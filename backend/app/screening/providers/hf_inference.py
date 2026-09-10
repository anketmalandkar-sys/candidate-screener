"""Detection tier on Hugging Face Inference.

Task models (prompt-injection classifier, NLI, embeddings) always run on the
HF-hosted ``hf-inference`` provider, so raw résumé text never leaves HF
infrastructure. The prompt-injection classifier runs once per candidate and is
recorded as its own ``injection_classifier`` agent-run row so the activity feed
shows the HF model that actually ran; its score is not merged back into the
deterministic feature bundle.

The three sub-agents (manipulation_guard, timeline_auditor, inflation_auditor)
are structured detectors: they combine the deterministic pre-scan with the
classifier above. They only make a chat call when ``hf_subagent_chat_model`` is
set — and because ``hf-inference`` serves no chat model, that requires an opt-in
``hf_subagent_chat_provider`` (a third-party provider reached through HF
routing), at which point résumé text leaves HF infra for that one call. With no
chat model configured the sub-agents run in **pre-scan mode** (not "degraded" —
"degraded" means a model call was attempted and failed).
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import time

from app.schemas.screening import IntegrityAuditResult
from app.screening import tools as screening_tools
from app.screening.agents import detectors
from app.screening.agents.prompts import detection_user_message
from app.screening.jsonio import run_ladder
from app.screening.types import AgentCall, PrescanResult

logger = logging.getLogger(__name__)

_TIER = "hf"
_PRESCAN_MODEL = "deterministic pre-scan (hf-inference has no chat model)"


class HFDetectionProvider:
    # Overridden by OpenAIAgenticDetectionProvider — the sub-agent chat tier.
    _tier = _TIER

    def __init__(self, settings, client=None) -> None:
        self._settings = settings
        if client is not None:
            self._client = client
        else:
            # The *sync* InferenceClient — no aiohttp dependency, stable across
            # huggingface_hub versions. Calls are offloaded with to_thread so
            # the coordinator's fan-out stays concurrent.
            from huggingface_hub import InferenceClient

            kwargs = {"token": settings.hf_token or None, "timeout": 60}
            if settings.hf_bill_to:
                kwargs["bill_to"] = settings.hf_bill_to
            try:
                self._client = InferenceClient(provider="hf-inference", **kwargs)
            except TypeError:
                self._client = InferenceClient(**kwargs)

        self._chat_model = settings.hf_subagent_chat_model.strip()
        self._chat_provider = getattr(settings, "hf_subagent_chat_provider", "").strip()
        # Task models stay pinned to hf-inference (self._client). The sub-agent
        # chat call, when enabled, goes through a *separate* client routed to the
        # opt-in third-party provider — résumé text leaves HF infra for it.
        self._chat_client = self._client
        if self._chat_model and client is None:
            from huggingface_hub import InferenceClient

            ckwargs = {"token": settings.hf_token or None, "timeout": 60}
            if settings.hf_bill_to:
                ckwargs["bill_to"] = settings.hf_bill_to
            try:
                self._chat_client = InferenceClient(
                    provider=self._chat_provider or "auto", **ckwargs
                )
            except TypeError:
                self._chat_client = InferenceClient(**ckwargs)

    async def _invoke(self, name: str, *args, client=None, **kwargs):
        target = client if client is not None else self._client
        fn = getattr(target, name)
        if inspect.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        return await asyncio.to_thread(lambda: fn(*args, **kwargs))

    # -- provider seams (overridden by the OpenAI-backed subclass) --------------

    async def _chat(self, messages, *, tools=None, response_format=None):
        """One chat turn → the response `message` object. HF `chat_completion`
        via the routed chat client."""
        kw: dict = {
            "messages": messages,
            "model": self._chat_model,
            "temperature": 0,
            "max_tokens": 1200,
            "client": self._chat_client,
        }
        if tools is not None:
            kw["tools"] = tools
            kw["tool_choice"] = "auto"
        if response_format is not None:
            kw["response_format"] = response_format
        resp = await self._invoke("chat_completion", **kw)
        return resp.choices[0].message

    async def _classify_segment(self, segment: str) -> list[dict]:
        """Score one span with the hf-inference prompt-injection classifier
        (always an HF task model, whatever the sub-agent chat tier is)."""
        res = await self._invoke(
            "text_classification", segment, model=self._settings.hf_injection_model
        )
        return _as_label_list(res)

    async def aclose(self) -> None:
        seen: set[int] = set()
        for c in (self._client, self._chat_client):
            if c is None or id(c) in seen:
                continue
            seen.add(id(c))
            close = getattr(c, "close", None)
            if close is None:
                continue
            try:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    def describe(self) -> dict[str, str]:
        # Agentic when a routed sub-agent chat model is configured (1–3 call the
        # deterministic checks as tools); otherwise pre-scan mode.
        return {"detection": "hf_agentic" if self._chat_model else "hf_inference"}

    # -- task models (best-effort; failures degrade to the deterministic bundle)

    async def _injection_scores(self, text: str) -> tuple[list[dict], AgentCall]:
        """Run the hf-inference prompt-injection classifier over the résumé
        segments. Returns the per-segment label scores and an ``AgentCall`` so
        the call shows on the activity feed. The scores are recorded for the
        audit trail only — they are not merged into the pre-scan feature
        bundle."""
        out: list[dict] = []
        sent: list[str] = []
        started = time.monotonic()
        failure: str | None = None
        for chunk in _segments(text):
            sent.append(chunk)
            try:
                labels = await self._classify_segment(chunk)
                out.append({"segment": chunk[:120], "labels": labels})
                if getattr(self._settings, "screening_log_prompts", False):
                    logger.info(
                        "HF text_classification [%s] request:\n%s\nresponse:\n%s",
                        self._settings.hf_injection_model,
                        chunk[:2000],
                        labels,
                    )
                else:
                    logger.info(
                        "HF text_classification [%s] -> %s",
                        self._settings.hf_injection_model,
                        labels[:2],
                    )
            except Exception as exc:
                logger.info("hf injection classifier failed: %s", exc)
                failure = str(exc)
                break

        latency_ms = int((time.monotonic() - started) * 1000)
        prompt_text = (
            "prompt-injection classifier — résumé segments scored on "
            f"{self._settings.hf_injection_model} (provider=hf-inference)\n\n"
            + "\n\n---\n\n".join(sent)
        )
        ok = bool(out) and failure is None
        call = AgentCall(
            agent_name="injection_classifier",
            tier=_TIER,
            model=self._settings.hf_injection_model,
            prompt_sha256=hashlib.sha256(prompt_text.encode()).hexdigest(),
            prompt_text=prompt_text,
            raw_response=json.dumps(
                out if ok else {"error": failure or "no segments scored"},
                ensure_ascii=False,
                indent=2,
            ),
            parsed_result={"segments": out} if ok else None,
            parsed_ok=ok,
            degraded=not ok,
            notes=None if ok else "hf classifier unreachable",
            latency_ms=latency_ms,
            input_chars=len(text),
        )
        return out, call

    # -- detection --------------------------------------------------------------

    async def detect(
        self,
        *,
        candidate_id: str,
        text: str,
        prescan: PrescanResult,
        role_context: dict,
    ) -> tuple[list[IntegrityAuditResult], list[AgentCall]]:
        # The injection classifier runs per candidate and is persisted as its
        # own ``injection_classifier`` agent-run row (added to ``calls`` below);
        # its score is not merged into the pre-scan feature bundle.
        _classifier_scores, classifier_call = await self._injection_scores(text)

        results: list[IntegrityAuditResult] = []
        calls: list[AgentCall] = [classifier_call]

        for spec in detectors.SPECS:
            if not self._chat_model:
                res = detectors.fallback(spec.agent_name, prescan, candidate_id)
                results.append(res)
                calls.append(
                    AgentCall(
                        agent_name=spec.agent_name,
                        tier=_TIER,
                        model=_PRESCAN_MODEL,
                        prompt_text=(
                            "Pre-scan mode: HF_SUBAGENT_CHAT_MODEL is unset and "
                            "hf-inference serves no chat model, so this agent's "
                            "result is the deterministic pre-scan combined with "
                            "the prompt-injection classifier. No chat request "
                            "was sent. Set HF_SUBAGENT_CHAT_MODEL + "
                            "HF_SUBAGENT_CHAT_PROVIDER to route a real chat call."
                        ),
                        raw_response=res.model_dump_json(),
                        parsed_result=res.model_dump(),
                        parsed_ok=True,
                        degraded=False,
                        notes="pre-scan mode",
                        input_chars=len(text),
                    )
                )
                continue

            user = detection_user_message(
                candidate_id=candidate_id,
                text=text,
                features=prescan.features,
                role_context=role_context,
            )
            started = time.monotonic()
            out = await self._run_agent(spec, user, prescan)
            parsed = out["parsed"]

            if parsed is not None:
                res = detectors.normalise(
                    parsed.model_dump(), spec.agent_name, candidate_id
                )
                degraded = False
                note = (
                    f"agentic; {out['note_suffix']}"
                    if out["note_suffix"]
                    else "agentic"
                )
            else:
                # Chat model failed (bad output, or unreachable / out of
                # credits) — fall back to the deterministic pre-scan. The
                # candidate is still screened; the row is marked degraded.
                res = detectors.fallback(spec.agent_name, prescan, candidate_id)
                degraded = True
                note = f"agentic; {out['note_suffix'] or 'json_ladder_exhausted'}"

            prompt_text = spec.system + "\n\n---\n\n" + user
            if out["transcript"]:
                prompt_text += "\n\n--- tool calls ---\n" + out["transcript"]

            results.append(res)
            calls.append(
                AgentCall(
                    agent_name=spec.agent_name,
                    tier=self._tier,
                    model=self._chat_model,
                    prompt_sha256=hashlib.sha256(
                        (spec.system + user).encode()
                    ).hexdigest(),
                    prompt_text=prompt_text,
                    raw_response=out["raw"],
                    parsed_result=res.model_dump(),
                    parsed_ok=parsed is not None,
                    repair_attempts=out["attempts"],
                    degraded=degraded,
                    notes=note,
                    tool_calls=out["tool_calls"],
                    latency_ms=int((time.monotonic() - started) * 1000),
                    input_chars=len(text),
                )
            )

        return results, calls

    async def _run_agent(self, spec, user: str, prescan: PrescanResult) -> dict:
        """Bounded tool-calling loop for one sub-agent, using the routed chat
        client. The deterministic checks are offered as tools; the model calls
        them for evidence, then returns the ``IntegrityAuditResult`` JSON. Any
        parse failure is left for the caller to turn into a pre-scan fallback.

        Returns ``{parsed, raw, attempts, tool_calls, transcript, note_suffix}``.
        """
        system = spec.system + (
            "\n\nYou may call the provided tools to gather deterministic "
            "evidence before you decide. The tools return raw signals, not "
            "verdicts — you must still read the candidate text yourself and "
            "judge. When finished, reply with ONLY the IntegrityAuditResult "
            "JSON object."
        )
        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        tool_specs = screening_tools.specs_for(
            spec.agent_name,
            with_classifier=True,
            injection_model=getattr(self._settings, "hf_injection_model", ""),
        )
        max_steps = max(
            1, int(getattr(self._settings, "hf_subagent_max_tool_steps", 4))
        )
        log = getattr(self._settings, "screening_log_prompts", False)

        tool_calls: list[dict] = []
        transcript: list[str] = []
        note_suffix: str | None = None
        hard_error: str | None = None
        tools_ok = bool(tool_specs)

        # Plain JSON mode, not strict json_schema: the routed HF providers and
        # some OpenAI-compatible servers reject the json_schema response_format
        # (and often reject it alongside tools=). The system prompt asks for a
        # bare JSON object and run_ladder + parse_json coerce the rest.
        json_rf = {"type": "json_object"}
        tier = self._tier.upper()

        final_content = ""
        for step in range(max_steps + 1):
            offer = tools_ok and step < max_steps
            if log:
                logger.info(
                    "%s sub-agent [%s / %s] step %d%s request:\n%s",
                    tier,
                    spec.agent_name,
                    self._chat_model,
                    step,
                    " (+tools)" if offer else "",
                    "\n\n".join(f"[{m['role']}]\n{m.get('content')}" for m in messages),
                )
            try:
                msg = await self._chat(
                    messages,
                    tools=tool_specs if offer else None,
                    response_format=None if offer else json_rf,
                )
            except Exception as exc:
                m = str(exc).lower()
                looks_like_config = any(
                    k in m
                    for k in (
                        "not supported by provider",
                        "unauthorized",
                        "401",
                        "403",
                        "quota",
                        "insufficient",
                        "payment",
                        "credit",
                        "depleted",
                        "does not exist",
                    )
                )
                # A 400-ish error while offering tools is usually the tools=
                # payload — drop tools and retry once.
                if offer and tools_ok and not looks_like_config:
                    tools_ok = False
                    note_suffix = "tools unsupported by provider"
                    transcript.append(f"[tools unsupported by provider: {exc}]")
                    continue
                # Anything else (wrong model/provider pair, auth, out of
                # credits, repeated 400): stop and fall back to the pre-scan for
                # this sub-agent. The candidate is still screened — never
                # dropped — with the row marked degraded and this reason.
                hard_error = f"{type(exc).__name__}: {str(exc).strip()}"[:180]
                logger.warning(
                    "%s sub-agent %s chat call failed: %s",
                    tier,
                    spec.agent_name,
                    exc,
                )
                break

            raw_calls = getattr(msg, "tool_calls", None) or []
            if raw_calls and offer:
                messages.append(_assistant_msg_with_calls(msg, raw_calls))
                for tc in raw_calls:
                    fn, args, tc_id = _decode_call(tc)
                    t0 = time.monotonic()
                    result = await screening_tools.run_tool(
                        fn, args, prescan=prescan, classify=self._classify_segment
                    )
                    dt = int((time.monotonic() - t0) * 1000)
                    summary = screening_tools.summarize(fn, result)
                    tool_calls.append(
                        {
                            "name": fn,
                            "arguments": args,
                            "result_summary": summary,
                            "latency_ms": dt,
                        }
                    )
                    transcript.append(
                        f"→ {fn}({json.dumps(args, ensure_ascii=False)}) "
                        f"→ {summary} [{dt} ms]"
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": json.dumps(result, ensure_ascii=False)[:6000],
                        }
                    )
                continue

            final_content = msg.content or ""
            if log:
                logger.info(
                    "%s sub-agent [%s / %s] response:\n%s",
                    tier,
                    spec.agent_name,
                    self._chat_model,
                    final_content,
                )
            break

        if hard_error is not None:
            return {
                "parsed": None,
                "raw": f"error: {hard_error}",
                "attempts": 0,
                "tool_calls": tool_calls,
                "transcript": "\n".join(transcript),
                "note_suffix": f"chat model unavailable ({hard_error})",
            }

        async def _final_call(extra: str | None) -> str:
            if extra is None:
                return final_content
            messages.append({"role": "user", "content": extra})
            m = await self._chat(messages, response_format=json_rf)
            c = m.content or ""
            messages.append({"role": "assistant", "content": c})
            return c

        try:
            parsed, raw, attempts = await run_ladder(_final_call, IntegrityAuditResult)
        except Exception as exc:
            logger.warning("hf sub-agent %s failed: %s", spec.agent_name, exc)
            parsed, raw, attempts = None, f"error: {exc}", 0

        return {
            "parsed": parsed,
            "raw": raw,
            "attempts": attempts,
            "tool_calls": tool_calls,
            "transcript": "\n".join(transcript),
            "note_suffix": note_suffix,
        }


def _decode_call(tc):
    """(fn_name, args_dict, tool_call_id) from an SDK tool-call object or a plain
    dict, tolerating `arguments` as either a JSON string or an already-parsed
    dict (huggingface_hub versions differ)."""
    if isinstance(tc, dict):
        func = tc.get("function") or {}
        fn = func.get("name", "") or ""
        raw_args = func.get("arguments")
        tc_id = tc.get("id") or fn
    else:
        func = getattr(tc, "function", None)
        fn = getattr(func, "name", "") or ""
        raw_args = getattr(func, "arguments", None)
        tc_id = getattr(tc, "id", None) or fn
    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError:
            args = {}
    elif isinstance(raw_args, dict):
        args = raw_args
    else:
        args = {}
    return fn, args, tc_id


def _assistant_msg_with_calls(msg, raw_calls):
    tool_calls = []
    for tc in raw_calls:
        fn, args, tc_id = _decode_call(tc)
        tool_calls.append(
            {
                "id": tc_id,
                "type": "function",
                "function": {
                    "name": fn,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        )
    return {
        "role": "assistant",
        "content": getattr(msg, "content", "") or "",
        "tool_calls": tool_calls,
    }


def _segments(text: str, size: int = 1500) -> list[str]:
    text = text.strip()
    return [text[i : i + size] for i in range(0, min(len(text), size * 6), size)] or [
        ""
    ]


def _as_label_list(res) -> list[dict]:
    try:
        return [{"label": r.label, "score": round(float(r.score), 4)} for r in res]
    except Exception:
        return []

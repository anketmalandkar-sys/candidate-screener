# Pointing the screener at a different LLM

The screening chat tiers — detection sub-agents 1–3 and synthesis Agents 4/5 —
each call an **OpenAI-compatible `/chat/completions` endpoint**. Which one is
chosen entirely from the environment; there is no code change and no UI switch.

- `OPENAI_API_KEY` / `OPENAI_BASE_URL` — shared default for both tiers.
- `OPENAI_SUBAGENT_MODEL` (detection) / `OPENAI_SYNTHESIS_MODEL` (synthesis).
- `SCREENING_DETECTION_BASE_URL` / `SCREENING_DETECTION_API_KEY` and
  `SCREENING_SYNTHESIS_BASE_URL` / `SCREENING_SYNTHESIS_API_KEY` — optional
  per-tier overrides; each falls back to the shared `OPENAI_*` value.
- **Blank = unset.** An empty `OPENAI_BASE_URL` resolves to
  `https://api.openai.com/v1`; an empty key resolves to "no key".

After editing `.env`: `docker compose up -d backend` (or `--build` if the image
changed).

---

## OpenAI (default)

```dotenv
SCREENING_PROVIDER=live
OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL unset -> https://api.openai.com/v1
# OPENAI_SYNTHESIS_MODEL=gpt-4.1
# OPENAI_SUBAGENT_MODEL=gpt-4.1-mini
```

## Ollama (local)

Run `ollama serve` on the host and `ollama pull llama3.1:8b`. From inside the
compose backend container the host is `host.docker.internal`, **not**
`localhost`.

```dotenv
SCREENING_PROVIDER=live
OPENAI_BASE_URL=http://host.docker.internal:11434/v1
OPENAI_API_KEY=ollama                # any non-empty string; Ollama ignores it
OPENAI_SYNTHESIS_MODEL=llama3.1:8b
OPENAI_SUBAGENT_MODEL=llama3.1:8b
HF_TOKEN=                            # the injection-classifier row will be `degraded`
```

## vLLM / TGI (self-hosted, OpenAI mode)

Start vLLM with `--served-model-name local` (that string is the model id).

```dotenv
SCREENING_PROVIDER=live
OPENAI_BASE_URL=http://vllm:8000/v1
OPENAI_API_KEY=EMPTY                 # vLLM's placeholder; or your gateway key
OPENAI_SYNTHESIS_MODEL=local
OPENAI_SUBAGENT_MODEL=local
```

## Azure OpenAI

```dotenv
SCREENING_PROVIDER=live
OPENAI_BASE_URL=https://<resource>.openai.azure.com/openai/deployments/<deployment>
OPENAI_API_KEY=<azure-key>
OPENAI_SYNTHESIS_MODEL=<deployment>  # Azure keys the model by deployment name
OPENAI_SUBAGENT_MODEL=<deployment>
# If the gateway requires it, append ?api-version=2024-08-01-preview to the URL.
```

## Groq

```dotenv
SCREENING_PROVIDER=live
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_API_KEY=gsk_...
OPENAI_SYNTHESIS_MODEL=llama-3.3-70b-versatile
OPENAI_SUBAGENT_MODEL=llama-3.1-8b-instant
```

## Hugging Face Inference Providers router

`https://router.huggingface.co/v1` is an OpenAI-compatible endpoint that routes to
third-party providers (together, nebius, novita, …). Authenticate with an
`hf_...` token; the same token also authenticates the prompt-injection classifier.
Gated models such as `meta-llama/Llama-3.1-8B-Instruct` require the token owner to
have accepted the model licence on huggingface.co, otherwise calls 403.

```dotenv
SCREENING_PROVIDER=live
OPENAI_BASE_URL=https://router.huggingface.co/v1
OPENAI_API_KEY=hf_...
OPENAI_SYNTHESIS_MODEL=meta-llama/Llama-3.1-70B-Instruct
OPENAI_SUBAGENT_MODEL=meta-llama/Llama-3.1-8B-Instruct
HF_TOKEN=hf_...                      # same token; runs the injection classifier
```

## Split tiers

Different model per tier: point the `SCREENING_DETECTION_*` / `SCREENING_SYNTHESIS_*`
overrides at different endpoints and **do not** set `OPENAI_BASE_URL` — it is
shared and would move both tiers.

### Open detection model (HF router) + hosted OpenAI synthesis

Detection Agents 1–3 on `meta-llama/Llama-3.1-8B-Instruct` via the HF router,
synthesis Agents 4–5 kept on hosted OpenAI / `gpt-4.1`.

```dotenv
SCREENING_PROVIDER=live

# Detection (Agents 1-3):
SCREENING_DETECTION_BASE_URL=https://router.huggingface.co/v1
SCREENING_DETECTION_API_KEY=hf_...
OPENAI_SUBAGENT_MODEL=meta-llama/Llama-3.1-8B-Instruct

# Synthesis (Agents 4-5) on hosted OpenAI:
OPENAI_API_KEY=sk-...
OPENAI_SYNTHESIS_MODEL=gpt-4.1

HF_TOKEN=hf_...                      # runs the injection classifier
```

An 8B detection model produces a few more `degraded` sub-agent rows than
`gpt-4.1-mini`; the deterministic pre-scan and `verifier.coverage_check` remain
the backstop, so candidates are still fully screened. If tool-calling is rejected
the loop retries once without tools; if *every* detection row is `degraded`, check
the model id, licence acceptance, and the row `notes`.

### Local detection (Ollama) + hosted OpenAI synthesis

```dotenv
SCREENING_PROVIDER=live

# Detection (Agents 1-3) on a local model:
SCREENING_DETECTION_BASE_URL=http://host.docker.internal:11434/v1
SCREENING_DETECTION_API_KEY=ollama
OPENAI_SUBAGENT_MODEL=llama3.1:8b

# Synthesis (Agents 4-5) on hosted OpenAI:
SCREENING_SYNTHESIS_BASE_URL=https://api.openai.com/v1
SCREENING_SYNTHESIS_API_KEY=sk-...
OPENAI_SYNTHESIS_MODEL=gpt-4.1
```

---

## What still needs Hugging Face

Only the **prompt-injection classifier** (`HF_INJECTION_MODEL`, default
`protectai/deberta-v3-base-prompt-injection-v2`). It is a real
`text_classification` task model, not a chat model, so it does not run on an
OpenAI-compatible chat endpoint.

- With `HF_TOKEN` set: it runs per candidate as its own `injection_classifier`
  agent-run row.
- Without a token: that one row comes back `degraded` and the deterministic
  pre-scan is the injection backstop — the candidate is **still fully screened
  and never dropped**.
- To run it locally with no network at all, set
  `SCREENING_DETECTION_BACKEND=hf_local` and
  `pip install -r backend/requirements-hf-local.txt`.

## Verifying the endpoint from the container

```bash
docker compose exec backend python3 -c \
 "import os,httpx; u=os.environ.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1'; \
  print(httpx.get(u.rstrip('/')+'/models', timeout=10).status_code)"
```

Then start a screening run over a couple of candidates and open the run page:
the **Agent activity** table shows the `model` each row actually used, and
`docker compose logs backend | grep -i 'OpenAI request'` shows the calls hitting
your endpoint.

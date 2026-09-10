import { Fragment, useState } from 'react'
import {
  AGENT_ROLE,
  type AgentRun,
  type AgentRunSummary,
  type ToolCall,
} from './types'

export function AgentLegend() {
  return (
    <p className="muted agent-legend">
      The <strong>injection classifier</strong> is the Hugging Face
      (hf-inference) model that scores every résumé for prompt injection.
      Sub-agents <strong>1–3</strong> (manipulation, timeline, inflation) are
      tool-using agents (OpenAI <code>gpt-4.1-mini</code> by default) — they call
      the deterministic checks (<em>N tools</em>) and decide;{' '}
      <span className="muted">pre-scan</span> means no chat model was configured
      for them. <strong>4</strong> (synthesizer) is the OpenAI call that
      re-reads the résumé and writes the audit; <strong>5</strong> (comparative
      reasoner) is the separate Compare step. A row is <em>degraded</em> only
      when a model call was attempted and failed, and the result fell back to
      the pre-scan.
    </p>
  )
}

type Row = AgentRunSummary | Partial<AgentRun>

function hasText(r: Row): r is AgentRun {
  return typeof (r as AgentRun).prompt_text === 'string'
}

export default function AgentRunTable({
  rows,
  loadFull,
  showCandidate = true,
}: {
  rows: Row[]
  loadFull?: (candidateId: string) => Promise<AgentRun[]>
  showCandidate?: boolean
}) {
  const [open, setOpen] = useState<Set<number>>(new Set())
  const [full, setFull] = useState<Record<string, AgentRun[]>>({})
  const [loading, setLoading] = useState<Set<string>>(new Set())

  if (rows.length === 0)
    return <p className="muted">No agent calls recorded yet.</p>

  async function toggle(r: Row) {
    const id = r.id!
    const next = new Set(open)
    if (next.has(id)) {
      next.delete(id)
      setOpen(next)
      return
    }
    next.add(id)
    setOpen(next)
    const cid = r.candidate_id!
    if (!hasText(r) && loadFull && !full[cid] && !loading.has(cid)) {
      setLoading((s) => new Set(s).add(cid))
      try {
        const fetched = await loadFull(cid)
        setFull((f) => ({ ...f, [cid]: fetched }))
      } finally {
        setLoading((s) => {
          const n = new Set(s)
          n.delete(cid)
          return n
        })
      }
    }
  }

  function textFor(r: Row): { req: string; res: string } | null {
    if (hasText(r)) return { req: r.prompt_text, res: r.raw_response }
    const detail = (full[r.candidate_id!] ?? []).find((x) => x.id === r.id)
    return detail ? { req: detail.prompt_text, res: detail.raw_response } : null
  }

  function toolsFor(r: Row): ToolCall[] {
    if (hasText(r)) return r.tool_calls ?? []
    const detail = (full[r.candidate_id!] ?? []).find((x) => x.id === r.id)
    return detail?.tool_calls ?? []
  }

  function toolCount(r: Row): number {
    return r.tool_call_count ?? (hasText(r) ? (r.tool_calls?.length ?? 0) : 0)
  }

  return (
    <table className="grid agent-runs">
      <thead>
        <tr>
          {showCandidate && <th>Candidate</th>}
          <th>Agent</th>
          <th>Model</th>
          <th>Status</th>
          <th>Latency</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const id = r.id!
          const isOpen = open.has(id)
          const t = isOpen ? textFor(r) : null
          return (
            <Fragment key={id}>
              <tr className="agent-run-row" onClick={() => toggle(r)}>
                {showCandidate && <td>{r.candidate_name ?? r.candidate_id}</td>}
                <td title={AGENT_ROLE[r.agent_name!] ?? ''}>
                  {r.agent_name!.replace(/_/g, ' ')}{' '}
                  <span className="tier-tag">{r.tier}</span>
                </td>
                <td>{r.model}</td>
                <td>
                  {r.degraded ? (
                    <span className="chip chip-review">degraded</span>
                  ) : r.notes?.startsWith('pre-scan') ? (
                    <span className="chip">pre-scan</span>
                  ) : r.parsed_ok ? (
                    <span className="chip chip-clear">ok</span>
                  ) : (
                    <span className="chip">no output</span>
                  )}
                  {(r.repair_attempts ?? 0) > 0 && (
                    <span className="muted"> · {r.repair_attempts} repair</span>
                  )}
                  {toolCount(r) > 0 && (
                    <span className="muted"> · {toolCount(r)} tools</span>
                  )}
                  {r.notes && <span className="muted"> · {r.notes}</span>}
                </td>
                <td>{r.latency_ms ? `${r.latency_ms} ms` : '—'}</td>
                <td>{isOpen ? '▾' : '▸'}</td>
              </tr>
              {isOpen && (
                <tr>
                  <td colSpan={showCandidate ? 6 : 5}>
                    {loading.has(r.candidate_id!) && <p>Loading…</p>}
                    {t && (
                      <div className="agent-run-detail">
                        {toolsFor(r).length > 0 && (
                          <>
                            <h4>Tools called</h4>
                            <ul className="agent-tool-calls">
                              {toolsFor(r).map((tc, i) => (
                                <li key={i}>
                                  <code>
                                    {tc.name}(
                                    {JSON.stringify(tc.arguments ?? {})})
                                  </code>{' '}
                                  → {tc.result_summary}{' '}
                                  <span className="muted">
                                    · {tc.latency_ms} ms
                                  </span>
                                </li>
                              ))}
                            </ul>
                          </>
                        )}
                        <h4>Request</h4>
                        <pre className="resume-view">{t.req}</pre>
                        <h4>Response</h4>
                        <pre className="resume-view">{t.res}</pre>
                      </div>
                    )}
                    {!t && !loading.has(r.candidate_id!) && (
                      <p className="muted">
                        Request / response available once this candidate
                        finishes.
                      </p>
                    )}
                  </td>
                </tr>
              )}
            </Fragment>
          )
        })}
      </tbody>
    </table>
  )
}

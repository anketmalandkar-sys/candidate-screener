import { useEffect, useState } from 'react'
import { api } from '../api'
import type { CandidatePoolItem } from '../candidates/types'
import type { RoleSummary } from '../types'
import type { ComparisonDetail } from './types'

export default function ComparePage() {
  const [roles, setRoles] = useState<RoleSummary[]>([])
  const [pool, setPool] = useState<CandidatePoolItem[]>([])
  const [roleId, setRoleId] = useState<number | null>(null)
  const [a, setA] = useState<number | null>(null)
  const [b, setB] = useState<number | null>(null)
  const [aText, setAText] = useState('')
  const [bText, setBText] = useState('')
  const [result, setResult] = useState<ComparisonDetail | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    Promise.all([
      api.listRoles({ active: true, limit: 100 }),
      api.listCandidates({ limit: 100 }),
    ])
      .then(([r, c]) => {
        setRoles(r.items)
        setPool(c.items)
        if (r.items[0]) setRoleId(r.items[0].id)
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : 'Failed to load'),
      )
  }, [])

  const name = (id: number | null) =>
    pool.find((c) => c.id === id)?.name ?? id

  // Resolve typed text (from the <datalist> input) back to a candidate id.
  // Exact case-insensitive name match; unmatched / cleared text -> null.
  const resolve = (text: string) =>
    pool.find((c) => c.name.toLowerCase() === text.trim().toLowerCase())?.id ??
    null

  // The model refers to the two candidates by id ("candidate 243", "#243").
  // Swap those for the real names in anything we show the user.
  const humanize = (text: string) => {
    if (!result) return text
    const byId = new Map<number, string>()
    for (const id of [result.candidate_a_id, result.candidate_b_id]) {
      const n = pool.find((c) => c.id === id)?.name
      if (n) byId.set(id, n)
    }
    return text.replace(
      /\b(?:candidate\s+#?|#)(\d+)\b/gi,
      (whole, id: string) => byId.get(Number(id)) ?? whole,
    )
  }

  async function run() {
    if (!roleId || !a || !b || a === b) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      setResult(await api.compareCandidates(roleId, a, b))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Comparison failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <h1>Compare two candidates</h1>
      <p className="muted">
        Plain-language trade-offs, citing evidence from both. Integrity
        violations and unsubstantiated inflation penalise rank regardless of
        nominal years of experience. This is a separate step — it never runs
        inside a screening run.
      </p>
      {error && <div className="banner banner-error">{error}</div>}

      <label className="field">
        <span>Role</span>
        <select
          value={roleId ?? ''}
          onChange={(e) => setRoleId(Number(e.target.value))}
        >
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.title}
            </option>
          ))}
        </select>
      </label>

      <div className="field-pair">
        <label className="field">
          <span>Candidate A</span>
          <input
            type="text"
            list="candidate-pool"
            placeholder="Type to search…"
            value={aText}
            onChange={(e) => {
              setAText(e.target.value)
              setA(resolve(e.target.value))
            }}
          />
        </label>
        <label className="field">
          <span>Candidate B</span>
          <input
            type="text"
            list="candidate-pool"
            placeholder="Type to search…"
            value={bText}
            onChange={(e) => {
              setBText(e.target.value)
              setB(resolve(e.target.value))
            }}
          />
        </label>
        <datalist id="candidate-pool">
          {pool.map((c) => (
            <option key={c.id} value={c.name} />
          ))}
        </datalist>
      </div>

      <button
        className="primary"
        disabled={busy || !roleId || !a || !b || a === b}
        onClick={run}
      >
        {busy ? 'Comparing…' : 'Compare'}
      </button>

      {result && (
        <div className="compare-result">
          <h2>
            {name(Number(result.higher_ranked_id))} ranks above{' '}
            {name(Number(result.lower_ranked_id))}
          </h2>
          <p>{humanize(result.decision_summary)}</p>
          <table className="grid">
            <thead>
              <tr>
                <th>Dimension</th>
                <th>{name(result.candidate_a_id)}</th>
                <th>{name(result.candidate_b_id)}</th>
                <th>Trade-off</th>
              </tr>
            </thead>
            <tbody>
              {result.comparisons.map((d, i) => (
                <tr key={i}>
                  <td>
                    <strong>{d.dimension.replace(/_/g, ' ')}</strong>
                  </td>
                  <td>{humanize(d.candidate_a_evidence)}</td>
                  <td>{humanize(d.candidate_b_evidence)}</td>
                  <td>{humanize(d.tradeoff_analysis)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {result.prompt_text && (
            <details className="about-screening">
              <summary>Model request &amp; response ({result.model})</summary>
              <h3>Request</h3>
              <pre className="resume-view">{result.prompt_text}</pre>
              <h3>Response</h3>
              <pre className="resume-view">{result.raw_response}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

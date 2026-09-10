import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import Pagination from '../components/Pagination'
import AgentRunTable, { AgentLegend } from './AgentRunTable'
import type { AgentRunSummary, RunDetail } from './types'
import { DispositionChip } from './ui'

const DONE = new Set(['complete', 'partial', 'failed'])
const PAGE = 25
type SortKey = 'name' | 'disposition'
const DISPO_RANK: Record<string, number> = {
  high_concern: 0,
  review: 1,
  clear: 2,
}

export default function RunDetailPage() {
  const { runId } = useParams()
  const id = Number(runId)
  const [run, setRun] = useState<RunDetail | null>(null)
  const [activity, setActivity] = useState<AgentRunSummary[]>([])
  const [showActivity, setShowActivity] = useState(true)
  const [error, setError] = useState('')
  const [sort, setSort] = useState<SortKey>('disposition')
  const [offset, setOffset] = useState(0)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const poll = useCallback(async () => {
    try {
      const [next, runs] = await Promise.all([
        api.getScreeningRun(id),
        api.listRunAgentRuns(id).catch(() => [] as AgentRunSummary[]),
      ])
      setRun(next)
      setActivity(runs)
      if (!DONE.has(next.status)) {
        timer.current = setTimeout(poll, 2000)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load the run')
    }
  }, [id])

  useEffect(() => {
    poll()
    return () => {
      if (timer.current) clearTimeout(timer.current)
    }
  }, [poll])

  if (error) return <div className="banner banner-error">{error}</div>
  if (!run) return <div className="empty">Loading…</div>

  const { counts } = run
  const pct = counts.total
    ? Math.round((counts.screened + counts.errored) / counts.total * 100)
    : 0

  // Chips SORT the table; they never hide a row.
  const sorted = [...run.results].sort((a, b) => {
    if (sort === 'name') return a.candidate_name.localeCompare(b.candidate_name)
    const ra = a.status === 'error' ? -1 : DISPO_RANK[a.overall_disposition ?? 'clear']
    const rb = b.status === 'error' ? -1 : DISPO_RANK[b.overall_disposition ?? 'clear']
    return ra - rb
  })
  const rows = sorted.slice(offset, offset + PAGE)

  function reSort(next: SortKey) {
    setSort(next)
    setOffset(0)
  }

  return (
    <div className="page">
      <p>
        <Link to="/screening">← all runs</Link>
      </p>
      <h1>Screening run #{run.id}</h1>
      <p className="muted">
        {run.status} · detection: {run.provider.detection ?? '—'} · synthesis:{' '}
        {run.provider.synthesis ?? '—'}
      </p>

      <div className="progress">
        <div className="progress-bar" style={{ width: `${pct}%` }} />
      </div>
      <p className="muted">
        {counts.screened + counts.errored} / {counts.total} screened ·{' '}
        {counts.compromised} with findings · {counts.errored} errored
      </p>

      <div className="pool-head">
        <button
          className="link-btn"
          onClick={() => setShowActivity((v) => !v)}
        >
          {showActivity ? '▾' : '▸'} Agent activity ({activity.length} calls)
        </button>
      </div>
      {showActivity && (
        <>
          <AgentLegend />
          <AgentRunTable
            rows={activity}
            loadFull={(cid) => api.listResultAgentRuns(id, cid)}
          />
        </>
      )}

      <div className="pool-head">
        Sort:{' '}
        <button className="link-btn" onClick={() => reSort('disposition')}>
          by concern
        </button>{' '}
        <button className="link-btn" onClick={() => reSort('name')}>
          by name
        </button>
      </div>

      <table className="grid">
        <thead>
          <tr>
            <th>Candidate</th>
            <th>Status</th>
            <th>Findings</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.candidate_id}>
              <td>{r.candidate_name}</td>
              <td>
                <DispositionChip
                  status={r.status}
                  disposition={r.overall_disposition}
                />
              </td>
              <td>{r.finding_count}</td>
              <td>
                <Link to={`/screening/runs/${run.id}/c/${r.candidate_id}`}>
                  Open audit
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pagination
        total={sorted.length}
        limit={PAGE}
        offset={offset}
        onChange={setOffset}
      />
    </div>
  )
}

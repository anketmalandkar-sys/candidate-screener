import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import Pagination from '../components/Pagination'
import type { RunSummary } from './types'

const PAGE = 15

/** The recruiter's screening runs, newest first, paginated. Shown on the Start
 * page so a run you kicked off earlier is never lost. */
export default function RunsPanel() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState('')

  const load = useCallback((nextOffset: number) => {
    api
      .listScreeningRuns({ limit: PAGE, offset: nextOffset })
      .then((p) => {
        if (p.items.length === 0 && nextOffset > 0) {
          return load(Math.max(0, nextOffset - PAGE))
        }
        setRuns(p.items)
        setTotal(p.total)
        setOffset(nextOffset)
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : 'Could not load runs'),
      )
  }, [])

  useEffect(() => {
    load(0)
  }, [load])

  if (error) return <div className="banner banner-error">{error}</div>
  if (!runs) return null
  if (runs.length === 0) return <p className="muted">No screening runs yet.</p>

  return (
    <>
      <table className="grid">
        <thead>
          <tr>
            <th>Run</th>
            <th>Started</th>
            <th>Status</th>
            <th>Screened</th>
            <th title="Candidates with at least one integrity finding (any severity). Not a rejection.">
              With findings
            </th>
            <th />
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>#{r.id}</td>
              <td>{new Date(r.created_at).toLocaleString()}</td>
              <td>{r.status}</td>
              <td>
                {r.counts.screened + r.counts.errored} / {r.counts.total}
              </td>
              <td>{r.counts.compromised}</td>
              <td>
                <Link to={`/screening/runs/${r.id}`}>Open</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pagination
        total={total}
        limit={PAGE}
        offset={offset}
        onChange={load}
      />
    </>
  )
}

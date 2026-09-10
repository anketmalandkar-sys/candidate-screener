import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import Pagination from '../components/Pagination'
import AddCandidate from './AddCandidate'
import type { CandidatePoolItem } from './types'

interface ResumeView {
  name: string
  text: string
}

const PAGE_SIZE = 20

export default function CandidateManagementPage() {
  const [candidates, setCandidates] = useState<CandidatePoolItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [adding, setAdding] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)
  const [resume, setResume] = useState<ResumeView | null>(null)
  const [resumeLoadingId, setResumeLoadingId] = useState<number | null>(null)

  const load = useCallback(async (nextOffset: number) => {
    const page = await api.listCandidates({ offset: nextOffset, limit: PAGE_SIZE })
    // Deleting the last row of the last page leaves it empty — step back.
    if (page.items.length === 0 && nextOffset > 0) {
      return load(Math.max(0, nextOffset - PAGE_SIZE))
    }
    setCandidates(page.items)
    setTotal(page.total)
    setOffset(nextOffset)
  }, [])

  const go = useCallback(
    (nextOffset: number) => {
      setError('')
      load(nextOffset).catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Failed to load'),
      )
    },
    [load],
  )

  useEffect(() => {
    setLoading(true)
    load(0)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Failed to load'),
      )
      .finally(() => setLoading(false))
  }, [load])

  useEffect(() => {
    if (!resume) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setResume(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [resume])

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return candidates
    return candidates.filter((c) => c.name.toLowerCase().includes(needle))
  }, [candidates, search])

  async function viewResume(c: CandidatePoolItem) {
    setResumeLoadingId(c.id)
    setError('')
    try {
      const detail = await api.getCandidate(c.id)
      setResume({ name: c.name, text: detail.resume_text })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the résumé')
    } finally {
      setResumeLoadingId(null)
    }
  }

  async function remove(c: CandidatePoolItem) {
    if (!window.confirm(`Delete ${c.name} from the pool?`)) return
    setBusyId(c.id)
    setError('')
    try {
      await api.deleteCandidate(c.id)
      await load(offset)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete the candidate')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Candidates</h1>
          <p className="muted">Your applicant pool.</p>
        </div>
        {!adding && (
          <button className="primary" onClick={() => setAdding(true)}>
            New candidate
          </button>
        )}
      </div>

      {error && <div className="error">{error}</div>}

      {adding && (
        <div style={{ marginBottom: 16 }}>
          <AddCandidate
            onAdded={() => void go(0)}
            onClose={() => setAdding(false)}
          />
        </div>
      )}

      <input
        type="text"
        aria-label="Search by name"
        placeholder="Search by name…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ maxWidth: 320, marginBottom: 16 }}
      />

      {loading ? (
        <div className="empty">Loading…</div>
      ) : visible.length === 0 ? (
        <div className="card empty">
          {candidates.length === 0
            ? 'No candidates yet. Use “New candidate” to add one.'
            : 'No candidates match your search.'}
        </div>
      ) : (
        <ul className="stack" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {visible.map((c) => (
            <li key={c.id} className="card">
              <div className="spread">
                <div style={{ minWidth: 0 }}>
                  <h2>{c.name}</h2>
                  <p className="muted" style={{ margin: '4px 0 0' }}>
                    {c.email ?? 'no email'}
                    {' · '}
                    {c.source === 'upload' && c.original_filename ? (
                      <span className="badge badge-source">
                        {c.original_filename}
                      </span>
                    ) : (
                      'pasted'
                    )}
                    {' · '}
                    {new Date(c.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="row" style={{ gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  <button
                    disabled={resumeLoadingId === c.id}
                    onClick={() => void viewResume(c)}
                  >
                    {resumeLoadingId === c.id ? 'Loading…' : 'View résumé'}
                  </button>
                  <button
                    className="danger"
                    disabled={busyId === c.id}
                    onClick={() => remove(c)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {!loading && (
        <Pagination
          total={total}
          limit={PAGE_SIZE}
          offset={offset}
          onChange={go}
        />
      )}

      {resume && (
        <div
          className="modal-backdrop"
          onClick={() => setResume(null)}
          role="presentation"
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={`Résumé — ${resume.name}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="spread" style={{ marginBottom: 12 }}>
              <h2 style={{ margin: 0 }}>{resume.name}</h2>
              <button className="link" onClick={() => setResume(null)}>
                Close
              </button>
            </div>
            <pre className="resume-text">{resume.text}</pre>
          </div>
        </div>
      )}
    </div>
  )
}

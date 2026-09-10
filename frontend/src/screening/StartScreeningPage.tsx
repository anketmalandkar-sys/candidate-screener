import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { CandidatePoolItem } from '../candidates/types'
import type { RoleSummary } from '../types'
import RunsPanel from './RunsPanel'
import { AboutScreening } from './ui'

const POOL_PAGE = 100

export default function StartScreeningPage() {
  const navigate = useNavigate()
  const [roles, setRoles] = useState<RoleSummary[]>([])
  const [pool, setPool] = useState<CandidatePoolItem[]>([])
  const [roleId, setRoleId] = useState<number | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    Promise.all([
      api.listRoles({ active: true, limit: 100 }),
      api.listCandidates({ limit: POOL_PAGE }),
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

  const shown = pool.filter((c) =>
    c.name.toLowerCase().includes(filter.trim().toLowerCase()),
  )

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function run() {
    if (!roleId || selected.size === 0) return
    setBusy(true)
    setError('')
    try {
      const created = await api.startScreening(roleId, [...selected])
      navigate(`/screening/runs/${created.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start screening')
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <h1>Start a screening</h1>
      <AboutScreening />

      {error && <div className="banner banner-error">{error}</div>}

      <label className="field">
        <span>Role</span>
        <select
          value={roleId ?? ''}
          onChange={(e) => setRoleId(Number(e.target.value))}
        >
          {roles.length === 0 && <option value="">No active roles</option>}
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.title}
            </option>
          ))}
        </select>
      </label>

      <div className="pool-head">
        <strong>{selected.size}</strong> of {pool.length} candidates selected
        <input
          className="pool-filter"
          placeholder="Filter by name…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <button
          type="button"
          className="link-btn"
          onClick={() => setSelected(new Set(shown.map((c) => c.id)))}
        >
          Select all shown
        </button>
        <button
          type="button"
          className="link-btn"
          onClick={() => setSelected(new Set())}
        >
          Clear
        </button>
      </div>

      <ul className="pool-list">
        {shown.map((c) => (
          <li key={c.id}>
            <label>
              <input
                type="checkbox"
                checked={selected.has(c.id)}
                onChange={() => toggle(c.id)}
              />
              {c.name}
              {c.email && <span className="muted"> · {c.email}</span>}
            </label>
          </li>
        ))}
      </ul>

      <button
        className="primary"
        disabled={busy || !roleId || selected.size === 0}
        onClick={run}
      >
        {busy ? 'Starting…' : `Run screening on ${selected.size}`}
      </button>

      <h2 className="runs-heading">Recent runs</h2>
      <RunsPanel />
    </div>
  )
}

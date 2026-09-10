import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import Pagination from '../components/Pagination'
import RoleForm from '../components/RoleForm'
import type { RequirementInput, RoleDetail, RoleSummary } from '../types'

type Mode =
  | { kind: 'none' }
  | { kind: 'create' }
  | { kind: 'edit'; role: RoleDetail }

const PAGE_SIZE = 20

export default function RoleManagementPage() {
  const [roles, setRoles] = useState<RoleSummary[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [mode, setMode] = useState<Mode>({ kind: 'none' })
  const [busyId, setBusyId] = useState<number | null>(null)

  const load = useCallback(async (nextOffset: number) => {
    // No filter: the management view shows active and inactive roles alike.
    const page = await api.listRoles({ offset: nextOffset, limit: PAGE_SIZE })
    // Deleting the last row of the last page leaves it empty — step back.
    if (page.items.length === 0 && nextOffset > 0) {
      return load(Math.max(0, nextOffset - PAGE_SIZE))
    }
    setRoles(page.items)
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
    load(0)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [load])

  async function startEdit(id: number) {
    setError('')
    try {
      const role = await api.getRole(id)
      setMode({ kind: 'edit', role })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open the role')
    }
  }

  async function submitForm(data: {
    title: string
    description: string
    requirements: RequirementInput[]
  }) {
    if (mode.kind === 'edit') {
      await api.updateRole(mode.role.id, data)
      await load(offset)
    } else {
      await api.createRole(data.title, data.description, data.requirements)
      await load(0)
    }
    setMode({ kind: 'none' })
  }

  async function toggleActive(role: RoleSummary) {
    setBusyId(role.id)
    setError('')
    try {
      await api.updateRole(role.id, { is_active: !role.is_active })
      await load(offset)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not change the role status')
    } finally {
      setBusyId(null)
    }
  }

  async function remove(role: RoleSummary) {
    if (!window.confirm(`Delete “${role.title}”? This can't be undone.`)) return
    setBusyId(role.id)
    setError('')
    try {
      await api.deleteRole(role.id)
      await load(offset)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete the role')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Roles</h1>
        </div>
        {mode.kind === 'none' && (
          <button className="primary" onClick={() => setMode({ kind: 'create' })}>
            New role
          </button>
        )}
      </div>

      {error && <div className="error">{error}</div>}

      {mode.kind === 'create' && (
        <RoleForm onSubmit={submitForm} onCancel={() => setMode({ kind: 'none' })} />
      )}
      {mode.kind === 'edit' && (
        <RoleForm
          initial={mode.role}
          onSubmit={submitForm}
          onCancel={() => setMode({ kind: 'none' })}
        />
      )}

      {loading ? (
        <div className="empty">Loading…</div>
      ) : roles.length === 0 ? (
        <div className="card empty">No roles yet. Create one to get started.</div>
      ) : (
        <>
        <ul className="stack" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {roles.map((role) => (
            <li key={role.id} className="card">
              <div className="spread">
                <div style={{ minWidth: 0 }}>
                  <h2>{role.title}</h2>
                  <p className="muted" style={{ margin: '4px 0 0' }}>
                    <span className={`badge badge-${role.is_active ? 'must' : 'nice'}`}>
                      {role.is_active ? 'Active' : 'Inactive'}
                    </span>{' '}
                    {role.requirement_count} requirement
                    {role.requirement_count === 1 ? '' : 's'}
                  </p>
                </div>
                <div className="row" style={{ gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  <button onClick={() => startEdit(role.id)} disabled={busyId === role.id}>
                    Edit
                  </button>
                  <button onClick={() => toggleActive(role)} disabled={busyId === role.id}>
                    {role.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                  <button
                    className="danger"
                    onClick={() => remove(role)}
                    disabled={busyId === role.id}
                  >
                    Delete
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
        <Pagination
          total={total}
          limit={PAGE_SIZE}
          offset={offset}
          onChange={go}
        />
        </>
      )}
    </div>
  )
}

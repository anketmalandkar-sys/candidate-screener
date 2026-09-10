import { useState } from 'react'
import type { RequirementInput, RoleDetail } from '../types'
import RequirementRows from './RequirementRows'

interface Props {
  /** Present => edit an existing role; absent => create a new one. */
  initial?: RoleDetail
  onSubmit: (data: {
    title: string
    description: string
    requirements: RequirementInput[]
  }) => Promise<void>
  onCancel: () => void
}

function toInput(requirements: RoleDetail['requirements']): RequirementInput[] {
  return requirements.map((r) => ({
    label: r.label,
    weight: r.weight,
    aliases: r.aliases,
  }))
}

/**
 * The one form used to both create and edit a role: title, job description and
 * the must-have requirements grid. Requirement rows with a blank label are
 * dropped on submit.
 */
export default function RoleForm({ initial, onSubmit, onCancel }: Props) {
  const [title, setTitle] = useState(initial?.title ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [requirements, setRequirements] = useState<RequirementInput[]>(
    initial ? toInput(initial.requirements) : [],
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const cleaned = requirements
      .map((item) => ({ ...item, label: item.label.trim() }))
      .filter((item) => item.label.length > 0)

    setBusy(true)
    setError('')
    try {
      await onSubmit({ title: title.trim(), description: description.trim(), requirements: cleaned })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the role')
      setBusy(false)
    }
  }

  return (
    <form className="card" style={{ marginBottom: 16 }} onSubmit={submit}>
      <h2 style={{ marginBottom: 12 }}>{initial ? 'Edit role' : 'New role'}</h2>

      {error && <div className="error">{error}</div>}

      <div className="field">
        <label htmlFor="role-title">Title</label>
        <input
          id="role-title"
          type="text"
          value={title}
          required
          autoFocus
          maxLength={200}
          placeholder="Senior Backend Engineer"
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      <div className="field">
        <label htmlFor="role-description">Job description</label>
        <textarea
          id="role-description"
          value={description}
          style={{ minHeight: 180 }}
          placeholder={
            'Paste the full JD here — responsibilities, context, nice-to-haves.\n' +
            'Two roles can share a title with different JDs.'
          }
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      <div className="field">
        <label>Must-have requirements</label>
        <RequirementRows value={requirements} onChange={setRequirements} />
      </div>

      <div className="row">
        <button className="primary" type="submit" disabled={busy || !title.trim()}>
          {busy ? 'Saving…' : initial ? 'Save role' : 'Create role'}
        </button>
        <button type="button" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  )
}

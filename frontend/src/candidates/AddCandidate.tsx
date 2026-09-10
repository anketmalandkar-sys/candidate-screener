import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import { api } from '../api'
import type { CandidatePoolItem } from './types'

const ACCEPTED = '.pdf,.docx,.txt'

interface Props {
  onAdded: (candidate: CandidatePoolItem) => void
  onClose: () => void
}

/** Strip the extension and tidy separators, as a default candidate name. */
function nameFromFile(filename: string): string {
  return filename.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim()
}

/** Add a résumé to the pool. */
export default function AddCandidate({ onAdded, onClose }: Props) {
  const [tab, setTab] = useState<'paste' | 'upload'>('paste')
  const [name, setName] = useState('')
  const [resumeText, setResumeText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  function reset() {
    setName('')
    setResumeText('')
    setError('')
  }

  async function submitPaste(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      onAdded(await api.createCandidate(name, resumeText))
      reset()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add the candidate')
    } finally {
      setBusy(false)
    }
  }

  async function submitFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    setBusy(true)
    setError('')

    // Failures are collected rather than aborting the batch — one unreadable
    // scan should not discard the nine files that parsed fine.
    const failures: string[] = []
    for (const file of Array.from(files)) {
      try {
        onAdded(
          await api.uploadCandidate(name.trim() || nameFromFile(file.name), file),
        )
      } catch (err) {
        failures.push(`${file.name}: ${err instanceof Error ? err.message : 'failed'}`)
      }
    }

    setError(failures.join('\n'))
    if (fileInput.current) fileInput.current.value = ''
    setBusy(false)
    if (failures.length === 0) {
      reset()
      onClose()
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    void submitFiles(event.dataTransfer.files)
  }

  return (
    <div className="card">
      <div className="spread" style={{ marginBottom: 12 }}>
        <h2>Add a candidate</h2>
        <button type="button" className="link" onClick={onClose} disabled={busy}>
          Cancel
        </button>
      </div>

      <div className="tabs">
        <button
          className={`tab ${tab === 'paste' ? 'active' : ''}`}
          onClick={() => setTab('paste')}
        >
          Paste resume
        </button>
        <button
          className={`tab ${tab === 'upload' ? 'active' : ''}`}
          onClick={() => setTab('upload')}
        >
          Upload file
        </button>
      </div>

      {error && (
        <div className="error" style={{ whiteSpace: 'pre-wrap' }}>
          {error}
        </div>
      )}

      {tab === 'paste' ? (
        <form onSubmit={submitPaste}>
          <div className="field">
            <label htmlFor="candidate-name">Candidate name</label>
            <input
              id="candidate-name"
              type="text"
              value={name}
              required
              placeholder="Priya Nair"
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="resume">Resume text</label>
            <textarea
              id="resume"
              value={resumeText}
              required
              placeholder="Paste the full resume here…"
              onChange={(e) => setResumeText(e.target.value)}
            />
          </div>
          <button
            className="primary"
            type="submit"
            disabled={busy || !name.trim() || !resumeText.trim()}
          >
            {busy ? 'Adding…' : 'Add to pool'}
          </button>
        </form>
      ) : (
        <>
          <div className="field">
            <label htmlFor="upload-name">Candidate name</label>
            <input
              id="upload-name"
              type="text"
              value={name}
              placeholder="Taken from the filename if left blank"
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div
            className={`dropzone ${dragging ? 'active' : ''}`}
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            {busy ? 'Reading…' : 'Drop resumes here, or click to choose'}
            <div style={{ marginTop: 4, fontSize: 12 }}>
              PDF, DOCX or TXT · up to 5 MB each
            </div>
          </div>

          <input
            ref={fileInput}
            type="file"
            accept={ACCEPTED}
            multiple
            hidden
            onChange={(e) => void submitFiles(e.target.files)}
          />
        </>
      )}
    </div>
  )
}

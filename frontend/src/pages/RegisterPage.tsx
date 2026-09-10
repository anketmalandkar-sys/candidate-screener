import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

const MIN_PASSWORD_LENGTH = 8
const MAX_PASSWORD_LENGTH = 10

// Mirrors the server policy in backend/app/schemas.py; the server stays
// authoritative, this is just fast feedback.
function passwordProblem(pw: string): string | null {
  if (pw.length < MIN_PASSWORD_LENGTH || pw.length > MAX_PASSWORD_LENGTH) {
    return `Password must be ${MIN_PASSWORD_LENGTH}–${MAX_PASSWORD_LENGTH} characters.`
  }
  if (!/[a-z]/.test(pw)) return 'Password needs a lowercase letter.'
  if (!/[A-Z]/.test(pw)) return 'Password needs an uppercase letter.'
  if (!/[0-9]/.test(pw)) return 'Password needs a digit.'
  if (!/[^A-Za-z0-9\s]/.test(pw)) return 'Password needs a special character.'
  return null
}

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const pwProblem = password.length > 0 ? passwordProblem(password) : null

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await register(email, name, password)
      navigate('/candidates')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the account')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={onSubmit}>
        <h1>Create an account</h1>
        <p className="muted">Candidate Screener</p>

        {error && <div className="error">{error}</div>}

        <div className="field">
          <label htmlFor="name">Your name</label>
          <input
            id="name"
            type="text"
            value={name}
            autoComplete="name"
            required
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            autoComplete="email"
            required
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            maxLength={MAX_PASSWORD_LENGTH}
            onChange={(e) => setPassword(e.target.value)}
          />
          <div className="hint" style={pwProblem ? { color: 'var(--bad)' } : undefined}>
            {pwProblem ??
              `${MIN_PASSWORD_LENGTH}–${MAX_PASSWORD_LENGTH} characters, with an uppercase letter, a lowercase letter, a digit, and a special character.`}
          </div>
        </div>

        <button
          className="primary"
          type="submit"
          disabled={busy || pwProblem !== null}
          style={{ width: '100%' }}
        >
          {busy ? 'Creating…' : 'Create account'}
        </button>

        <p className="auth-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  )
}

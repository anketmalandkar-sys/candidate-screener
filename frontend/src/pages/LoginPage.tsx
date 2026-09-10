import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(email, password)
      navigate('/candidates')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={onSubmit}>
        <h1>Sign in</h1>
        <p className="muted">Candidate Screener</p>

        {error && <div className="error">{error}</div>}

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
            autoComplete="current-password"
            required
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button className="primary" type="submit" disabled={busy} style={{ width: '100%' }}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="auth-footer">
          No account yet? <Link to="/register">Create one</Link>
        </p>
      </form>
    </div>
  )
}

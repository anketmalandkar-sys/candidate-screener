import { Link, NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { useAuth } from './auth'
import CandidateManagementPage from './candidates/CandidateManagementPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import RoleManagementPage from './pages/RoleManagementPage'
import CandidateAuditPage from './screening/CandidateAuditPage'
import ComparePage from './screening/ComparePage'
import RunDetailPage from './screening/RunDetailPage'
import StartScreeningPage from './screening/StartScreeningPage'
import type { ReactNode } from 'react'

function TopBar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  if (!user) return null

  return (
    <div className="topbar">
      <Link to="/candidates" className="topbar-brand">
        Candidate Screener
      </Link>
      <div className="topbar-right">
        <span>{user.email}</span>
        <button
          onClick={async () => {
            await logout()
            navigate('/login')
          }}
        >
          Sign out
        </button>
      </div>
    </div>
  )
}

/** Left-hand navigation, shown only to signed-in users. */
function SideNav() {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'sidenav-link active' : 'sidenav-link'

  return (
    <nav className="sidenav">
      <NavLink to="/screening" end className={linkClass}>
        Screening
      </NavLink>
      <NavLink to="/roles" className={linkClass}>
        Roles
      </NavLink>
      <NavLink to="/candidates" className={linkClass}>
        Candidates
      </NavLink>
      <NavLink to="/screening/compare" className={linkClass}>
        Compare
      </NavLink>
    </nav>
  )
}

/** Gate a route on an authenticated session. */
function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  // Waiting on the initial /me probe — rendering the login page here would
  // flash it at every already-signed-in user on a page refresh.
  if (loading) return <div className="empty">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** Keep signed-in users away from the login and register pages. */
function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="empty">Loading…</div>
  if (user) return <Navigate to="/candidates" replace />
  return <>{children}</>
}

export default function App() {
  const { user } = useAuth()

  const routes = (
    <Routes>
      <Route
        path="/login"
        element={
          <RedirectIfAuthed>
            <LoginPage />
          </RedirectIfAuthed>
        }
      />
      <Route
        path="/register"
        element={
          <RedirectIfAuthed>
            <RegisterPage />
          </RedirectIfAuthed>
        }
      />
      <Route
        path="/candidates"
        element={
          <RequireAuth>
            <CandidateManagementPage />
          </RequireAuth>
        }
      />
      <Route
        path="/roles"
        element={
          <RequireAuth>
            <RoleManagementPage />
          </RequireAuth>
        }
      />
      <Route
        path="/screening"
        element={
          <RequireAuth>
            <StartScreeningPage />
          </RequireAuth>
        }
      />
      <Route
        path="/screening/compare"
        element={
          <RequireAuth>
            <ComparePage />
          </RequireAuth>
        }
      />
      <Route
        path="/screening/runs/:runId"
        element={
          <RequireAuth>
            <RunDetailPage />
          </RequireAuth>
        }
      />
      <Route
        path="/screening/runs/:runId/c/:candidateId"
        element={
          <RequireAuth>
            <CandidateAuditPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/candidates" replace />} />
    </Routes>
  )

  // Signed-out users (login / register) get no app chrome.
  if (!user) return routes

  return (
    <>
      <TopBar />
      <div className="shell">
        <SideNav />
        <main className="shell-main">{routes}</main>
      </div>
    </>
  )
}

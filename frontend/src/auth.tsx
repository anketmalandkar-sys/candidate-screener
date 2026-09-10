import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api, ApiError } from './api'
import type { User } from './types'

interface AuthState {
  user: User | null
  /** True until the initial /me probe settles, so we don't flash the login page. */
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, name: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // The session lives in an httpOnly cookie, so JS cannot read it directly.
    // Asking the server who we are is the only way to resolve session state.
    api
      .me()
      .then(setUser)
      .catch((error: unknown) => {
        if (!(error instanceof ApiError) || error.status !== 401) {
          console.error('Session check failed', error)
        }
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setUser(await api.login(email, password))
  }, [])

  const register = useCallback(async (email: string, name: string, password: string) => {
    setUser(await api.register(email, name, password))
  }, [])

  const logout = useCallback(async () => {
    await api.logout()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}

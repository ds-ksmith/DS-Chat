import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import * as authApi from '../api/auth'
import { ApiError, NetworkError } from '../api/client'
import { clearLastUser, loadLastUser, saveLastUser } from '../lib/lastUser'
import type { User } from '../types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  offline: boolean
  login: (usernameOrEmail: string, password: string) => Promise<void>
  logout: () => Promise<void>
  updateUser: (user: User) => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', user?.theme ?? 'dark')
  }, [user?.theme])

  useEffect(() => {
    authApi
      .me()
      .then((u) => {
        setUser(u)
        setOffline(false)
        saveLastUser(u)
      })
      .catch((err) => {
        // A confirmed 401 means the server is reachable and says "not
        // logged in" -- that's the only case that should actually clear the
        // cached identity. Everything else (a real network failure, or the
        // backend being down behind a reverse proxy that answers with its
        // own 502/503/504 -- both happen in production, not just literal
        // offline) means we simply couldn't get a confirmed answer.
        // /api/auth/me is NetworkOnly by design (never trust a stale
        // "who am I" as the *source of truth*), but treating "couldn't
        // check" the same as "confirmed logged out" would lock users out of
        // the cached rooms/messages entirely whenever the backend is
        // unreachable. Every real action still re-checks the actual session
        // cookie server-side, so falling back here can't grant anything.
        if (err instanceof ApiError && err.status === 401) {
          clearLastUser()
          return
        }
        if (!(err instanceof NetworkError)) {
          console.error('Failed to load current user', err)
        }
        const cached = loadLastUser()
        setUser(cached)
        setOffline(cached !== null)
      })
      .finally(() => setLoading(false))
  }, [])

  async function login(usernameOrEmail: string, password: string) {
    const u = await authApi.login(usernameOrEmail, password)
    setUser(u)
    setOffline(false)
    saveLastUser(u)
  }

  async function logout() {
    await authApi.logout()
    setUser(null)
    clearLastUser()
  }

  function updateUser(u: User) {
    setUser(u)
    saveLastUser(u)
  }

  return (
    <AuthContext.Provider value={{ user, loading, offline, login, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}

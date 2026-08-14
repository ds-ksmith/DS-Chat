import type { User } from '../types'

// A minimal, non-sensitive "who was I last logged in as" cache, so the app
// shell can render offline (ProtectedRoute has something to show) even
// though GET /api/auth/me is intentionally NetworkOnly and can't confirm the
// session while offline. This never grants access to anything real -- every
// server-side action still re-checks the actual session cookie, so a stale
// or wrong cached user here can, at worst, show cached UI; it can't act.
const KEY = 'kit_last_user'

export function saveLastUser(user: User): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(user))
  } catch {
    // storage unavailable (private browsing, quota) -- offline fallback
    // just won't work this session, not fatal.
  }
}

export function loadLastUser(): User | null {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as User) : null
  } catch {
    return null
  }
}

export function clearLastUser(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // ignore
  }
}

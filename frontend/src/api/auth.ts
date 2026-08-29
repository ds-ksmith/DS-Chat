import { apiFetch, ApiError, NetworkError } from './client'
import type { User, UserSession } from '../types'

// No register() here: this is an invite-only site. Accounts are created by
// an operator via the backend CLI (`python -m app.cli create-user`), not
// through a public endpoint.

export function login(usernameOrEmail: string, password: string): Promise<User> {
  return apiFetch<User>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username_or_email: usernameOrEmail, password }),
  })
}

export function logout(): Promise<void> {
  return apiFetch<void>('/api/auth/logout', { method: 'POST' })
}

// #69: every device/browser currently logged into this account, newest
// last-seen first -- see backend's app/schemas/session.py.
export function listSessions(): Promise<UserSession[]> {
  return apiFetch<UserSession[]>('/api/auth/sessions')
}

export function revokeSession(sessionId: string): Promise<void> {
  return apiFetch<void>(`/api/auth/sessions/${sessionId}`, { method: 'DELETE' })
}

export function me(): Promise<User> {
  return apiFetch<User>('/api/auth/me')
}

export function updateProfile(displayName: string | null): Promise<User> {
  return apiFetch<User>('/api/auth/me', {
    method: 'PATCH',
    body: JSON.stringify({ display_name: displayName }),
  })
}

// Deliberately its own call sending only `theme` -- the backend only
// applies fields actually present in the request body, so this can't
// clobber display_name (and updateProfile above can't clobber theme).
// Presets only ('dark'/'light'/'midnight'/'sunset') -- activating a custom
// theme is POST /api/custom-themes/{id}/activate (see api/customThemes.ts),
// since that needs an id and an ownership check, not just a bare name.
export function updateTheme(theme: 'dark' | 'light' | 'midnight' | 'sunset'): Promise<User> {
  return apiFetch<User>('/api/auth/me', {
    method: 'PATCH',
    body: JSON.stringify({ theme }),
  })
}

export function removeAvatar(): Promise<User> {
  return apiFetch<User>('/api/auth/me/avatar', { method: 'DELETE' })
}

// Deliberately its own call, same reasoning as updateTheme above -- a
// manual override of the presence indicator, global (every room, not
// per-room), independent of display_name/theme.
export function updateAppearOffline(appearOffline: boolean): Promise<User> {
  return apiFetch<User>('/api/auth/me', {
    method: 'PATCH',
    body: JSON.stringify({ appear_offline: appearOffline }),
  })
}

export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return apiFetch<void>('/api/auth/password', {
    method: 'PATCH',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
}

export function requestPasswordReset(email: string): Promise<void> {
  return apiFetch<void>('/api/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function validateResetToken(token: string): Promise<void> {
  return apiFetch<void>(`/api/auth/reset-password/validate?token=${encodeURIComponent(token)}`)
}

export function completePasswordReset(token: string, newPassword: string): Promise<User> {
  return apiFetch<User>('/api/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, new_password: newPassword }),
  })
}

// Not apiFetch: that wrapper always sets Content-Type: application/json,
// which would stomp the multipart boundary the browser needs to set itself
// for a file upload. Mirrors api/rooms.ts's uploadRoomImage.
export async function uploadAvatar(file: File): Promise<User> {
  const formData = new FormData()
  formData.append('file', file)

  let response: Response
  try {
    response = await fetch('/api/auth/me/avatar', {
      method: 'POST',
      credentials: 'include',
      body: formData,
    })
  } catch {
    throw new NetworkError()
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // response had no JSON body
    }
    throw new ApiError(response.status, detail)
  }

  return (await response.json()) as User
}

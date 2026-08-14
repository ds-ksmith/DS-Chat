import { apiFetch, ApiError, NetworkError } from './client'
import type { User } from '../types'

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

export function me(): Promise<User> {
  return apiFetch<User>('/api/auth/me')
}

export function updateProfile(displayName: string | null): Promise<User> {
  return apiFetch<User>('/api/auth/me', {
    method: 'PATCH',
    body: JSON.stringify({ display_name: displayName }),
  })
}

export function removeAvatar(): Promise<User> {
  return apiFetch<User>('/api/auth/me/avatar', { method: 'DELETE' })
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

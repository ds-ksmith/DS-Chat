import { apiFetch } from './client'
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

import { apiFetch } from './client'
import type { User } from '../types'

export function validateSignupToken(token: string): Promise<{ email: string }> {
  return apiFetch<{ email: string }>(`/api/signup/validate?token=${encodeURIComponent(token)}`)
}

export function completeSignup(
  token: string,
  username: string,
  password: string,
  passwordConfirm: string,
): Promise<User> {
  return apiFetch<User>('/api/signup', {
    method: 'POST',
    body: JSON.stringify({ token, username, password, password_confirm: passwordConfirm }),
  })
}

import { apiFetch } from './client'
import type { CustomTheme, CustomThemeColors, User } from '../types'

export function listCustomThemes(): Promise<CustomTheme[]> {
  return apiFetch<CustomTheme[]>('/api/custom-themes')
}

export function createCustomTheme(name: string, colors: CustomThemeColors): Promise<CustomTheme> {
  return apiFetch<CustomTheme>('/api/custom-themes', {
    method: 'POST',
    body: JSON.stringify({ name, colors }),
  })
}

// Each field independently optional-and-settable, same convention as
// updateProfile -- a rename shouldn't require resending all 12 colors.
export function updateCustomTheme(
  id: string,
  data: { name?: string; colors?: CustomThemeColors },
): Promise<CustomTheme> {
  return apiFetch<CustomTheme>(`/api/custom-themes/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteCustomTheme(id: string): Promise<void> {
  return apiFetch<void>(`/api/custom-themes/${id}`, { method: 'DELETE' })
}

export function activateCustomTheme(id: string): Promise<User> {
  return apiFetch<User>(`/api/custom-themes/${id}/activate`, { method: 'POST' })
}

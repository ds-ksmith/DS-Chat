import { apiFetch } from './client'
import type { UserDirectoryEntry } from '../types'

export function getUserAvatarUrl(userId: string, avatarFilename?: string | null): string {
  return `/api/users/${userId}/avatar${avatarFilename ? `?v=${avatarFilename}` : ''}`
}

export function listUserDirectory(): Promise<UserDirectoryEntry[]> {
  return apiFetch<UserDirectoryEntry[]>('/api/users')
}

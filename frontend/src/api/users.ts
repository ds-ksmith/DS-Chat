import { apiFetch } from './client'
import type { UserDirectoryEntry } from '../types'

export function getUserAvatarUrl(userId: string, avatarFilename?: string | null): string {
  return `/api/users/${userId}/avatar${avatarFilename ? `?v=${avatarFilename}` : ''}`
}

export function listUserDirectory(): Promise<UserDirectoryEntry[]> {
  return apiFetch<UserDirectoryEntry[]>('/api/users')
}

// A snapshot, not a live feed -- see backend/app/routers/users.py. Good
// enough for surfaces that only need to be accurate as of page load (the
// admin user list, the room-invite user search); chat surfaces get live
// presence for free via the room member list instead.
export function listOnlineUserIds(): Promise<string[]> {
  return apiFetch<string[]>('/api/users/online')
}

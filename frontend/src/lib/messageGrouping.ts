import { getUserAvatarUrl } from '../api/users'
import { hashIndex } from './avatar'
import type { RoomMember } from '../types'

export function senderColorIndex(username: string, members: RoomMember[]): number {
  const idx = members.findIndex((m) => m.username === username)
  if (idx >= 0) return idx
  // Fallback for a sender no longer in the room (e.g. they left): derive a
  // stable index from the username instead of always colliding on 0.
  return hashIndex(username)
}

export function avatarUrlFor(username: string, members: RoomMember[]): string | null {
  const member = members.find((m) => m.username === username)
  if (!member?.avatar_filename) return null
  return getUserAvatarUrl(member.user_id, member.avatar_filename)
}

export function displayNameFor(username: string, members: RoomMember[]): string {
  const member = members.find((m) => m.username === username)
  return member?.display_name || username
}

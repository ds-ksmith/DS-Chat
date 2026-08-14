import type { RoomMember } from '../types'

export function senderColorIndex(username: string, members: RoomMember[]): number {
  const idx = members.findIndex((m) => m.username === username)
  if (idx >= 0) return idx
  // Fallback for a sender no longer in the room (e.g. they left): derive a
  // stable index from the username instead of always colliding on 0.
  let hash = 0
  for (let i = 0; i < username.length; i++) hash = (hash * 31 + username.charCodeAt(i)) | 0
  return Math.abs(hash)
}

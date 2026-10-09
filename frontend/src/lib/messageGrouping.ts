import { getUserAvatarUrl } from '../api/users'
import { hashIndex } from './avatar'
import { isSameLocalDay } from './formatMessageTime'
import type { RoomMember } from '../types'

// #73: Slack's own threshold for the same "still grouped, but it's been a
// while" call -- past this gap a same-sender message starts a new group
// (its own avatar/name/timestamp) even with nobody else posting in
// between, so a message sent minutes later doesn't hide under a stale
// timestamp from the start of the run.
export const GROUP_BREAK_MS = 5 * 60 * 1000

interface Groupable {
  user_id: string
  created_at: string
}

// Whether `msg` gets its own avatar/name/timestamp header, vs. continuing
// `prev`'s group. A new calendar day always breaks the group: now that
// timestamps can carry a date, a same-sender run that crosses midnight
// (11:58 PM, then 12:01 AM) would otherwise leave the later message under a
// header showing the wrong day.
export function isGroupStart(prev: Groupable | undefined, msg: Groupable): boolean {
  if (!prev || prev.user_id !== msg.user_id) return true
  if (new Date(msg.created_at).getTime() - new Date(prev.created_at).getTime() > GROUP_BREAK_MS) return true
  return !isSameLocalDay(prev.created_at, msg.created_at)
}

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

export function statusFor(username: string, members: RoomMember[]): 'online' | 'offline' | undefined {
  return members.find((m) => m.username === username)?.status
}

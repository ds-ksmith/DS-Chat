import type { MyRoomItem } from '../types'

// Pulled out of ChatShellPage as a pure function purely so it's directly
// unit-testable without rendering the whole page -- behavior is unchanged.
// Only touches the matching room; every other room's object reference (and
// therefore its unread state) is left untouched.
export function clearRoomIndicators(rooms: MyRoomItem[], roomId: string): MyRoomItem[] {
  return rooms.map((r) => (r.id === roomId ? { ...r, has_unread: false, has_mention: false } : r))
}

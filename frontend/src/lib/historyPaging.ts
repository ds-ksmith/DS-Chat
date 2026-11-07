import type { Message } from '../types'

// Page size for message history requests. The server caps `limit` at 200, and
// "a short page means there's nothing older" below depends on asking for
// exactly this many every time.
export const HISTORY_PAGE_SIZE = 50

// Folds a freshly fetched newest-page into the history already on screen
// without discarding older messages the user has scrolled back to load -- a
// refetch happens on every rejoin (coming back to a backgrounded tab, a
// reconnect), and collapsing a scrolled-back view to the latest page each
// time would throw away their place.
//
// The fresh page is authoritative for whatever it covers. Anything already
// loaded that's older than it is kept, but only if the two actually join up:
// if the fresh page's first message isn't in what we have, a full page's
// worth of newer messages arrived in between, so keeping the old tail would
// leave a hole in the middle of the conversation -- better to start over from
// the fresh page and let the user scroll back again.
export function mergeFreshHistory(
  prev: Message[],
  fresh: Message[],
): { messages: Message[]; keptOlder: boolean } {
  if (fresh.length === 0 || prev.length === 0) return { messages: fresh, keptOlder: false }
  const overlapAt = prev.findIndex((m) => m.id === fresh[0].id)
  if (overlapAt < 0) return { messages: fresh, keptOlder: false }
  return { messages: [...prev.slice(0, overlapAt), ...fresh], keptOlder: overlapAt > 0 }
}

// An older page goes in front. Ids already present are dropped as a guard
// against a page overlapping what's on screen.
export function prependOlder(prev: Message[], older: Message[]): Message[] {
  const have = new Set(prev.map((m) => m.id))
  return [...older.filter((m) => !have.has(m.id)), ...prev]
}

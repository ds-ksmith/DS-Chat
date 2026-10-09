// "Today" is the viewer's local calendar day, so everything here goes through
// local-time getters, never UTC.
type DateLike = Date | string

function toDate(d: DateLike): Date {
  return d instanceof Date ? d : new Date(d)
}

// A calendar-day number, not elapsed milliseconds: built from the local
// y/m/d via Date.UTC so a 23- or 25-hour DST day still counts as one day,
// and 11:58 PM vs 12:01 AM (3 minutes apart) correctly counts as 1 day apart.
function dayNumber(d: Date): number {
  return Math.floor(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / 86_400_000)
}

export function isSameLocalDay(a: DateLike, b: DateLike): boolean {
  return dayNumber(toDate(a)) === dayNumber(toDate(b))
}

// A bare "4:04 PM" gives no way to tell today's message from one sent last
// week. Today stays time-only; anything older gains just enough date to
// place it.
export function formatMessageTime(iso: string, now: Date = new Date()): string {
  const sent = new Date(iso)
  const time = sent.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  // <= 0 also covers a timestamp slightly in the future (clock skew between
  // server and this device) -- better shown as today than as a negative age.
  const daysAgo = dayNumber(now) - dayNumber(sent)
  if (daysAgo <= 0) return time
  if (daysAgo === 1) return `Yesterday ${time}`
  // Under 7 so the weekday is never the same as today's (7 days ago would be).
  if (daysAgo < 7) return `${sent.toLocaleDateString([], { weekday: 'short' })} ${time}`
  const date = sent.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
    year: sent.getFullYear() === now.getFullYear() ? undefined : 'numeric',
  })
  return `${date}, ${time}`
}

// Hover text: the one place the full, unambiguous date is always available.
export function formatMessageTimeTitle(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: 'full', timeStyle: 'short' })
}

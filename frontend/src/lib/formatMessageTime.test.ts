import { describe, expect, it } from 'vitest'
import { formatMessageTime, formatMessageTimeTitle, isSameLocalDay } from './formatMessageTime'

// Local-time constructors throughout, and expected text built with the same
// locale calls the code uses -- so these hold in any timezone and any ICU
// locale instead of hardcoding "3:00 PM".
const NOW = new Date(2026, 9, 9, 15, 0) // Fri Oct 9 2026, 3:00 PM local

const iso = (d: Date) => d.toISOString()
const timeText = (d: Date) => d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
const weekday = (d: Date) => d.toLocaleDateString([], { weekday: 'short' })

describe('formatMessageTime', () => {
  it('shows just the time for a message sent today', () => {
    const morning = new Date(2026, 9, 9, 8, 5)
    expect(formatMessageTime(iso(morning), NOW)).toBe(timeText(morning))
  })

  it('prefixes "Yesterday" for yesterday', () => {
    const d = new Date(2026, 9, 8, 23, 59)
    expect(formatMessageTime(iso(d), NOW)).toBe(`Yesterday ${timeText(d)}`)
  })

  it('treats 11:59 PM vs 12:03 AM as different days despite being minutes apart', () => {
    const justBeforeMidnight = new Date(2026, 9, 8, 23, 59)
    const justAfterMidnight = new Date(2026, 9, 9, 0, 3)
    expect(formatMessageTime(iso(justBeforeMidnight), justAfterMidnight)).toBe(
      `Yesterday ${timeText(justBeforeMidnight)}`,
    )
    expect(formatMessageTime(iso(justAfterMidnight), justAfterMidnight)).toBe(timeText(justAfterMidnight))
  })

  it('uses the short weekday for 2 to 6 days ago', () => {
    const twoDays = new Date(2026, 9, 7, 12, 0)
    const sixDays = new Date(2026, 9, 3, 12, 0)
    expect(formatMessageTime(iso(twoDays), NOW)).toBe(`${weekday(twoDays)} ${timeText(twoDays)}`)
    expect(formatMessageTime(iso(sixDays), NOW)).toBe(`${weekday(sixDays)} ${timeText(sixDays)}`)
  })

  it('switches to a month and day at 7 days, without the year when it is this year', () => {
    const d = new Date(2026, 9, 2, 12, 0)
    const label = formatMessageTime(iso(d), NOW)
    expect(label).toBe(`${d.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${timeText(d)}`)
    expect(label).not.toContain('2026')
  })

  it('adds the year for a message from a different year', () => {
    const d = new Date(2025, 11, 25, 9, 30)
    const label = formatMessageTime(iso(d), NOW)
    expect(label).toBe(
      `${d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}, ${timeText(d)}`,
    )
    expect(label).toContain('2025')
  })

  it('counts Dec 31 -> Jan 1 as yesterday', () => {
    const d = new Date(2026, 11, 31, 22, 0)
    expect(formatMessageTime(iso(d), new Date(2027, 0, 1, 10, 0))).toBe(`Yesterday ${timeText(d)}`)
  })

  it('treats a slightly-future timestamp (clock skew) as today', () => {
    const tomorrow = new Date(2026, 9, 10, 9, 0)
    expect(formatMessageTime(iso(tomorrow), NOW)).toBe(timeText(tomorrow))
  })
})

describe('formatMessageTimeTitle', () => {
  it('includes the full date, with the year', () => {
    expect(formatMessageTimeTitle(iso(new Date(2026, 9, 2, 16, 4)))).toContain('2026')
  })
})

describe('isSameLocalDay', () => {
  it('is false across midnight and true within a day', () => {
    expect(isSameLocalDay(new Date(2026, 9, 8, 23, 59), new Date(2026, 9, 9, 0, 1))).toBe(false)
    expect(isSameLocalDay(new Date(2026, 9, 9, 0, 1), new Date(2026, 9, 9, 23, 59))).toBe(true)
  })

  it('accepts ISO strings as well as Dates', () => {
    expect(isSameLocalDay(iso(new Date(2026, 9, 9, 8, 0)), new Date(2026, 9, 9, 20, 0))).toBe(true)
  })
})

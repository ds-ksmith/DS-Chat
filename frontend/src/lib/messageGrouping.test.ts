import { describe, expect, it } from 'vitest'
import { GROUP_BREAK_MS, isGroupStart } from './messageGrouping'

const msg = (user: string, d: Date) => ({ user_id: user, created_at: d.toISOString() })

describe('isGroupStart', () => {
  const t = new Date(2026, 9, 9, 10, 0, 0)
  const later = (ms: number) => new Date(t.getTime() + ms)

  it('starts a group for the first message', () => {
    expect(isGroupStart(undefined, msg('a', t))).toBe(true)
  })

  it('starts a group when the sender changes', () => {
    expect(isGroupStart(msg('a', t), msg('b', later(1000)))).toBe(true)
  })

  it('keeps the same sender grouped within the break window', () => {
    expect(isGroupStart(msg('a', t), msg('a', later(60_000)))).toBe(false)
  })

  it('groups at exactly the break threshold and splits just past it', () => {
    expect(isGroupStart(msg('a', t), msg('a', later(GROUP_BREAK_MS)))).toBe(false)
    expect(isGroupStart(msg('a', t), msg('a', later(GROUP_BREAK_MS + 1000)))).toBe(true)
  })

  it('measures the gap from the previous message, not the first in the run', () => {
    const fourMin = 4 * 60_000
    expect(isGroupStart(msg('a', later(fourMin)), msg('a', later(2 * fourMin)))).toBe(false)
    expect(isGroupStart(msg('a', later(2 * fourMin)), msg('a', later(3 * fourMin)))).toBe(false)
  })

  it('starts a new group when the same sender crosses midnight, even a few minutes apart', () => {
    const before = new Date(2026, 9, 8, 23, 58)
    const after = new Date(2026, 9, 9, 0, 1)
    expect(after.getTime() - before.getTime()).toBeLessThan(GROUP_BREAK_MS)
    expect(isGroupStart(msg('a', before), msg('a', after))).toBe(true)
  })
})

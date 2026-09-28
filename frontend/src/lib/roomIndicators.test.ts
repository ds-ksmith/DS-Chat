import { describe, expect, it } from 'vitest'
import type { MyRoomItem } from '../types'
import { clearRoomIndicators } from './roomIndicators'

function makeRoom(overrides: Partial<MyRoomItem> & { id: string }): MyRoomItem {
  return {
    name: overrides.id,
    description: null,
    is_private: false,
    is_dm: false,
    is_archived: false,
    owner_id: 'owner',
    created_at: '2026-01-01T00:00:00Z',
    role: 'member',
    has_unread: false,
    has_mention: false,
    dm_partner: null,
    email_notifications: false,
    ...overrides,
  }
}

describe('clearRoomIndicators', () => {
  it('clears has_unread and has_mention on the matching room', () => {
    const rooms = [makeRoom({ id: 'room-1', has_unread: true, has_mention: true })]
    const result = clearRoomIndicators(rooms, 'room-1')
    expect(result[0].has_unread).toBe(false)
    expect(result[0].has_mention).toBe(false)
  })

  it('preserves unread state on every other room', () => {
    const rooms = [
      makeRoom({ id: 'room-1', has_unread: true, has_mention: true }),
      makeRoom({ id: 'room-2', has_unread: true, has_mention: false }),
      makeRoom({ id: 'room-3', has_unread: false, has_mention: false }),
    ]
    const result = clearRoomIndicators(rooms, 'room-1')
    const room2 = result.find((r) => r.id === 'room-2')
    const room3 = result.find((r) => r.id === 'room-3')
    expect(room2?.has_unread).toBe(true)
    expect(room3?.has_unread).toBe(false)
  })

  it('leaves untouched rooms as the same object reference', () => {
    const room2 = makeRoom({ id: 'room-2', has_unread: true })
    const rooms = [makeRoom({ id: 'room-1', has_unread: true }), room2]
    const result = clearRoomIndicators(rooms, 'room-1')
    expect(result[1]).toBe(room2)
  })

  it('is a no-op if the room id is not found', () => {
    const rooms = [makeRoom({ id: 'room-1', has_unread: true })]
    const result = clearRoomIndicators(rooms, 'does-not-exist')
    expect(result[0].has_unread).toBe(true)
  })
})

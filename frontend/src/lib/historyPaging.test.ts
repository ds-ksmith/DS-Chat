import { describe, expect, it } from 'vitest'
import type { Message } from '../types'
import { mergeFreshHistory, prependOlder } from './historyPaging'

function msg(id: string): Message {
  return {
    id,
    room_id: 'r1',
    user_id: 'u1',
    username: 'alice',
    content: id,
    image_id: null,
    file: null,
    link_preview: null,
    reactions: [],
    created_at: '2026-10-20T16:46:00Z',
    edited_at: null,
    deleted_at: null,
  }
}

const ids = (list: Message[]) => list.map((m) => m.id)
const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => msg(`m${from + i}`))

describe('mergeFreshHistory', () => {
  it('uses the fresh page when nothing was loaded yet', () => {
    const result = mergeFreshHistory([], range(5, 8))
    expect(ids(result.messages)).toEqual(['m5', 'm6', 'm7', 'm8'])
    expect(result.keptOlder).toBe(false)
  })

  it('keeps older messages that were already loaded', () => {
    // On screen: m1..m8 (user scrolled back). Fresh newest page: m5..m9.
    const result = mergeFreshHistory(range(1, 8), range(5, 9))
    expect(ids(result.messages)).toEqual(['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8', 'm9'])
    expect(result.keptOlder).toBe(true)
  })

  it('takes the fresh copy for the overlap, so edits and reactions are current', () => {
    const edited = { ...msg('m6'), content: 'edited' }
    const result = mergeFreshHistory(range(4, 8), [msg('m5'), edited, msg('m7')])
    expect(result.messages.find((m) => m.id === 'm6')?.content).toBe('edited')
  })

  it('reports nothing kept when the fresh page starts where history starts', () => {
    const result = mergeFreshHistory(range(5, 8), range(5, 9))
    expect(ids(result.messages)).toEqual(['m5', 'm6', 'm7', 'm8', 'm9'])
    expect(result.keptOlder).toBe(false)
  })

  it('starts over rather than leave a hole when a full page of newer messages arrived', () => {
    const result = mergeFreshHistory(range(1, 8), range(60, 64))
    expect(ids(result.messages)).toEqual(['m60', 'm61', 'm62', 'm63', 'm64'])
    expect(result.keptOlder).toBe(false)
  })

  it('uses an empty fresh page as-is', () => {
    expect(mergeFreshHistory(range(1, 3), []).messages).toEqual([])
  })
})

describe('prependOlder', () => {
  it('puts the older page in front, in order', () => {
    expect(ids(prependOlder(range(5, 8), range(1, 4)))).toEqual(['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8'])
  })

  it('drops messages that are already present', () => {
    expect(ids(prependOlder(range(5, 8), range(3, 6)))).toEqual(['m3', 'm4', 'm5', 'm6', 'm7', 'm8'])
  })

  it('leaves history alone for an empty page', () => {
    expect(ids(prependOlder(range(5, 6), []))).toEqual(['m5', 'm6'])
  })
})

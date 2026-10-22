import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { Message } from '../types'
import { MessageList } from './MessageList'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', username: 'alice', emoji_scale: 'normal' } }),
}))
vi.mock('../context/CustomEmojiContext', () => ({
  useCustomEmoji: () => ({ byShortcode: new Map(), list: [], refresh: () => {} }),
}))

beforeAll(() => {
  // jsdom doesn't implement it; MessageList scrolls to the bottom on mount.
  Element.prototype.scrollIntoView = () => {}
})

afterEach(cleanup)

function message(overrides: Partial<Message>): Message {
  return {
    id: 'm1',
    room_id: 'r1',
    user_id: 'u2',
    username: 'bob',
    content: 'hello',
    image_id: null,
    file: null,
    link_preview: null,
    reactions: [],
    created_at: '2026-10-20T16:46:00Z',
    edited_at: null,
    deleted_at: null,
    ...overrides,
  }
}

function renderList(messages: Message[], onReact = vi.fn()) {
  render(
    <MessageList
      roomId="r1"
      messages={messages}
      members={[]}
      myRooms={new Map()}
      onEdit={() => {}}
      onReact={onReact}
      onDelete={() => {}}
    />,
  )
  return onReact
}

const reacted = [{ emoji: '🎉', count: 1, user_ids: ['u2'] }]

describe('MessageList add-reaction button (#78)', () => {
  it('shows one in the reaction row only when the message already has reactions', () => {
    renderList([
      message({ id: 'm1', content: 'with', reactions: reacted }),
      message({ id: 'm2', content: 'without', reactions: [] }),
    ])
    const pills = document.querySelectorAll('.message-reaction-pills')
    expect(pills).toHaveLength(1)
    expect(within(pills[0] as HTMLElement).getByRole('button', { name: 'Add reaction' })).toBeTruthy()
  })

  it('keeps the hover-row button on every message', () => {
    renderList([
      message({ id: 'm1', reactions: reacted }),
      message({ id: 'm2', content: 'plain', reactions: [] }),
    ])
    // Two on the reacted message (row + pills), one on the plain one.
    expect(screen.getAllByRole('button', { name: 'Add reaction' })).toHaveLength(3)
  })

  it('opens the picker next to the pills and reacts with the pick', () => {
    const onReact = renderList([message({ reactions: reacted })])
    const pillsAdd = within(document.querySelector('.message-reaction-pills') as HTMLElement).getByRole(
      'button',
      { name: 'Add reaction' },
    )
    fireEvent.click(pillsAdd)

    const pickers = document.querySelectorAll('.emoji-picker')
    expect(pickers).toHaveLength(1)
    expect(document.querySelector('.message-reaction-pills .emoji-picker')).not.toBeNull()

    fireEvent.click(within(pickers[0] as HTMLElement).getAllByRole('menuitem')[0])
    expect(onReact).toHaveBeenCalledTimes(1)
    expect(onReact.mock.calls[0][0]).toBe('m1')
    expect(document.querySelector('.emoji-picker')).toBeNull()
  })

  it('opens only one picker at a time, in whichever place was used last', () => {
    renderList([message({ reactions: reacted })])
    const [rowButton, pillsButton] = [
      document.querySelector('.message-row-actions .message-reaction-trigger') as HTMLElement,
      document.querySelector('.message-reaction-pills .message-reaction-add') as HTMLElement,
    ]

    fireEvent.click(pillsButton)
    expect(document.querySelectorAll('.emoji-picker')).toHaveLength(1)

    fireEvent.click(rowButton)
    expect(document.querySelectorAll('.emoji-picker')).toHaveLength(1)
    expect(document.querySelector('.message-row-actions .emoji-picker')).not.toBeNull()
    expect(document.querySelector('.message-reaction-pills .emoji-picker')).toBeNull()
  })

  it('clicking the same button again closes its picker', () => {
    renderList([message({ reactions: reacted })])
    const pillsButton = document.querySelector('.message-reaction-pills .message-reaction-add') as HTMLElement
    fireEvent.click(pillsButton)
    expect(document.querySelector('.emoji-picker')).not.toBeNull()
    fireEvent.click(pillsButton)
    expect(document.querySelector('.emoji-picker')).toBeNull()
  })

  it('is not offered on a deleted message', () => {
    renderList([message({ content: null, deleted_at: '2026-10-21T10:00:00Z', reactions: [] })])
    expect(screen.queryByRole('button', { name: 'Add reaction' })).toBeNull()
  })
})

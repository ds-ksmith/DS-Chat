import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import type { ComponentProps } from 'react'
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

function renderList(messages: Message[], onReact = vi.fn(), extra: Partial<ComponentProps<typeof MessageList>> = {}) {
  render(
    <MessageList
      roomId="r1"
      messages={messages}
      members={[]}
      myRooms={new Map()}
      onEdit={() => {}}
      onReact={onReact}
      onDelete={() => {}}
      {...extra}
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

describe('MessageList older history', () => {
  it('offers to load earlier messages when there are more, and asks for them on click', () => {
    const onLoadOlder = vi.fn()
    // A list that overflows its view, so only the click (not the
    // too-short-to-scroll auto-load) asks.
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(2000)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(500)
    renderList([message({})], vi.fn(), { hasMoreOlder: true, onLoadOlder })
    fireEvent.click(screen.getByRole('button', { name: 'Load earlier messages' }))
    expect(onLoadOlder).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Start of conversation')).toBeNull()
    vi.restoreAllMocks()
  })

  it('shows a loading note instead of the button while an older page is loading', () => {
    renderList([message({})], vi.fn(), { hasMoreOlder: true, loadingOlder: true, onLoadOlder: vi.fn() })
    expect(screen.getByText('Loading earlier messages…')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Load earlier messages' })).toBeNull()
  })

  it('shows the error with a retry that asks again', () => {
    const onLoadOlder = vi.fn()
    renderList([message({})], vi.fn(), {
      hasMoreOlder: true,
      olderError: 'Could not load earlier messages.',
      onLoadOlder,
    })
    expect(screen.getByText('Could not load earlier messages.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onLoadOlder).toHaveBeenCalledTimes(1)
  })

  it('marks the start of the conversation once there is nothing older', () => {
    renderList([message({})], vi.fn(), { hasMoreOlder: false })
    expect(screen.getByText('Start of conversation')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Load earlier messages' })).toBeNull()
  })

  it('shows neither marker for an empty list', () => {
    renderList([], vi.fn(), { hasMoreOlder: false })
    expect(screen.queryByText('Start of conversation')).toBeNull()
  })

  it('jumps to the bottom when told the user sent something, even from scrolled back', () => {
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(3000)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(500)
    const props = {
      roomId: 'r1',
      messages: [message({})],
      members: [],
      myRooms: new Map<string, string>(),
      onEdit: () => {},
      onReact: () => {},
      onDelete: () => {},
    }
    const { rerender } = render(<MessageList {...props} scrollToBottomSignal={0} />)
    // Scroll back, away from the bottom.
    const list = document.querySelector('.message-list') as HTMLElement
    list.scrollTop = 100
    fireEvent.scroll(list)
    scrollIntoView.mockClear()

    rerender(<MessageList {...props} scrollToBottomSignal={1} />)
    expect(scrollIntoView).toHaveBeenCalled()
    vi.restoreAllMocks()
    Element.prototype.scrollIntoView = () => {}
  })

  it('does not ask for older messages on its own when the list already fills the view', () => {
    // jsdom reports zero heights, which reads as "too short to scroll" -- so
    // give the container real room and check the auto-load stays quiet.
    const onLoadOlder = vi.fn()
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(2000)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(500)
    renderList([message({})], vi.fn(), { hasMoreOlder: true, onLoadOlder })
    expect(onLoadOlder).not.toHaveBeenCalled()
    vi.restoreAllMocks()
  })

  it('asks for older messages by itself when the list is too short to scroll', () => {
    const onLoadOlder = vi.fn()
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(300)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(500)
    renderList([message({})], vi.fn(), { hasMoreOlder: true, onLoadOlder })
    expect(onLoadOlder).toHaveBeenCalled()
    vi.restoreAllMocks()
  })

  it('asks when scrolled near the top', () => {
    const onLoadOlder = vi.fn()
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(3000)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(500)
    renderList([message({})], vi.fn(), { hasMoreOlder: true, onLoadOlder })
    const list = document.querySelector('.message-list') as HTMLElement
    list.scrollTop = 100
    fireEvent.scroll(list)
    expect(onLoadOlder).toHaveBeenCalledTimes(1)
    vi.restoreAllMocks()
  })

  it('does not ask while one is already loading, or after a failure', () => {
    const onLoadOlder = vi.fn()
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(300)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(500)
    renderList([message({})], vi.fn(), { hasMoreOlder: true, loadingOlder: true, onLoadOlder })
    cleanup()
    renderList([message({})], vi.fn(), { hasMoreOlder: true, olderError: 'x', onLoadOlder })
    expect(onLoadOlder).not.toHaveBeenCalled()
    vi.restoreAllMocks()
  })
})

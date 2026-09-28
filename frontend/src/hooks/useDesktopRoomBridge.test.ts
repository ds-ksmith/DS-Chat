import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as desktopBridge from '../lib/desktopBridge'
import { useDesktopRoomBridge } from './useDesktopRoomBridge'

describe('useDesktopRoomBridge', () => {
  beforeEach(() => {
    vi.spyOn(desktopBridge, 'notifyRoomOpened')
    vi.spyOn(desktopBridge, 'notifyUnreadCount')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('calls roomOpened once when entering a room', () => {
    renderHook(({ roomId, count }) => useDesktopRoomBridge(roomId, count), {
      initialProps: { roomId: 'room-1', count: 0 },
    })
    expect(desktopBridge.notifyRoomOpened).toHaveBeenCalledTimes(1)
  })

  it('does not call roomOpened again on a rerender with the same roomId', () => {
    const { rerender } = renderHook(({ roomId, count }) => useDesktopRoomBridge(roomId, count), {
      initialProps: { roomId: 'room-1', count: 0 },
    })
    expect(desktopBridge.notifyRoomOpened).toHaveBeenCalledTimes(1)

    // Unrelated rerender -- unreadRoomCount changed, roomId did not.
    rerender({ roomId: 'room-1', count: 3 })
    rerender({ roomId: 'room-1', count: 3 })
    expect(desktopBridge.notifyRoomOpened).toHaveBeenCalledTimes(1)
  })

  it('calls roomOpened again on a genuine transition to a different room', () => {
    const { rerender } = renderHook(({ roomId, count }) => useDesktopRoomBridge(roomId, count), {
      initialProps: { roomId: 'room-1', count: 0 },
    })
    rerender({ roomId: 'room-2', count: 0 })
    expect(desktopBridge.notifyRoomOpened).toHaveBeenCalledTimes(2)
  })

  it('does not call roomOpened when there is no room id', () => {
    renderHook(({ roomId, count }) => useDesktopRoomBridge(roomId, count), {
      initialProps: { roomId: undefined as string | undefined, count: 0 },
    })
    expect(desktopBridge.notifyRoomOpened).not.toHaveBeenCalled()
  })

  it('sends the unread count whenever it changes, independent of roomOpened', () => {
    const { rerender } = renderHook(({ roomId, count }) => useDesktopRoomBridge(roomId, count), {
      initialProps: { roomId: undefined as string | undefined, count: 0 },
    })
    expect(desktopBridge.notifyUnreadCount).toHaveBeenCalledWith(0)

    rerender({ roomId: undefined, count: 2 })
    expect(desktopBridge.notifyUnreadCount).toHaveBeenCalledWith(2)
    expect(desktopBridge.notifyRoomOpened).not.toHaveBeenCalled()
  })
})

describe('desktop bridge functions with no window.dsDesktop', () => {
  it('remain optional -- calling them does not throw when the bridge is absent', () => {
    expect(window.dsDesktop).toBeUndefined()
    expect(() => desktopBridge.notifyRoomOpened()).not.toThrow()
    expect(() => desktopBridge.notifyUnreadCount(5)).not.toThrow()
  })
})

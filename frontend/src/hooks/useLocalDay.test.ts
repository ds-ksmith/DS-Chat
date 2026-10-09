import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useLocalDay } from './useLocalDay'

function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state })
}

describe('useLocalDay', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setVisibility('visible')
  })

  afterEach(() => {
    vi.useRealTimers()
    // Remove the own-property override so jsdom's real getter shows through again.
    delete (document as unknown as Record<string, unknown>).visibilityState
  })

  it('rolls over to the next day when local midnight passes', () => {
    vi.setSystemTime(new Date(2026, 9, 9, 23, 59, 30))
    const { result } = renderHook(() => useLocalDay())
    expect(result.current.getDate()).toBe(9)

    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(result.current.getDate()).toBe(10)
  })

  it('refreshes when the tab becomes visible after the clock moved a day (e.g. a sleeping laptop)', () => {
    vi.setSystemTime(new Date(2026, 9, 9, 12, 0))
    const { result } = renderHook(() => useLocalDay())

    // The clock jumps without any timer firing in between.
    vi.setSystemTime(new Date(2026, 9, 10, 12, 0))
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(result.current.getDate()).toBe(10)
  })

  it('keeps the same value (no rerender) when visibility changes on the same day', () => {
    vi.setSystemTime(new Date(2026, 9, 9, 12, 0))
    const { result } = renderHook(() => useLocalDay())
    const first = result.current

    vi.setSystemTime(new Date(2026, 9, 9, 18, 0))
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(result.current).toBe(first)
  })

  it('ignores visibility changes while the tab is hidden', () => {
    vi.setSystemTime(new Date(2026, 9, 9, 12, 0))
    const { result } = renderHook(() => useLocalDay())

    setVisibility('hidden')
    vi.setSystemTime(new Date(2026, 9, 10, 12, 0))
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(result.current.getDate()).toBe(9)
  })
})

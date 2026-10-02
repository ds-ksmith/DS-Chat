import { afterEach, describe, expect, it, vi } from 'vitest'
import { getFormattingToolbarOpen, setFormattingToolbarOpen } from './formattingToolbarPref'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('formatting toolbar preference', () => {
  it('is collapsed by default', () => {
    expect(getFormattingToolbarOpen()).toBe(false)
  })

  it('remembers being opened and closed', () => {
    setFormattingToolbarOpen(true)
    expect(getFormattingToolbarOpen()).toBe(true)
    setFormattingToolbarOpen(false)
    expect(getFormattingToolbarOpen()).toBe(false)
  })

  it('falls back to collapsed when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(getFormattingToolbarOpen()).toBe(false)
    expect(() => setFormattingToolbarOpen(true)).not.toThrow()
  })
})

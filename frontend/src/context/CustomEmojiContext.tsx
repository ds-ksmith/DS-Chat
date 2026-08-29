import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { listCustomEmoji } from '../api/customEmoji'
import type { CustomEmoji } from '../types'

interface CustomEmojiContextValue {
  // Every consumer needs one of two things: "does this shortcode exist"
  // (MessageContent's :shortcode: -> <img> conversion, keyed by name) or
  // "the full list to render" (EmojiPicker's Custom category) -- a Map
  // serves both without a second data structure.
  byShortcode: Map<string, CustomEmoji>
  list: CustomEmoji[]
  // Called after a successful upload/delete so every consumer (picker,
  // already-rendered messages using a shortcode that didn't exist a
  // moment ago) picks up the change without a full page reload.
  refresh: () => Promise<void>
}

const CustomEmojiContext = createContext<CustomEmojiContextValue | undefined>(undefined)

export function CustomEmojiProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<CustomEmoji[]>([])

  const refresh = useCallback(async () => {
    try {
      setList(await listCustomEmoji())
    } catch {
      // Non-critical -- the app works fine with an empty/stale custom-emoji
      // set, same treatment as ProfileModal's custom-themes fetch.
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const byShortcode = useMemo(() => new Map(list.map((e) => [e.shortcode, e])), [list])

  return (
    <CustomEmojiContext.Provider value={{ byShortcode, list, refresh }}>
      {children}
    </CustomEmojiContext.Provider>
  )
}

export function useCustomEmoji(): CustomEmojiContextValue {
  const ctx = useContext(CustomEmojiContext)
  if (!ctx) throw new Error('useCustomEmoji must be used within a CustomEmojiProvider')
  return ctx
}

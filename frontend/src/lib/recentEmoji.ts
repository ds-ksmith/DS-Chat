const KEY = 'recent-emoji'
const MAX_RECENT = 8

export function getRecentEmoji(): string[] {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((e) => typeof e === 'string') : []
  } catch {
    return []
  }
}

// Most-recently-used first, deduped, capped -- a picked emoji that's
// already in the list moves to the front rather than appearing twice.
export function recordEmojiUsed(emoji: string): void {
  try {
    const current = getRecentEmoji().filter((e) => e !== emoji)
    const next = [emoji, ...current].slice(0, MAX_RECENT)
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // storage unavailable (private browsing, quota) -- recent emoji just
    // won't persist this session, not fatal.
  }
}

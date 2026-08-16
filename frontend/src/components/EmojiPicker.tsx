import { useMemo, useState } from 'react'
import { useEscapeKey } from '../hooks/useEscapeKey'
import { ALL_EMOJI, EMOJI_CATEGORIES } from '../lib/emoji'
import { EMOJI_NAMES } from '../lib/emojiNames'
import './EmojiPicker.css'

interface EmojiPickerProps {
  onPick: (emoji: string) => void
  onClose: () => void
  placement?: 'above' | 'below'
  align?: 'left' | 'right'
}

function searchEmoji(query: string): string[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const seen = new Set<string>()
  const results: string[] = []
  for (const emoji of ALL_EMOJI) {
    if (seen.has(emoji)) continue
    const entry = EMOJI_NAMES[emoji]
    if (!entry) continue
    const matches = entry.name.toLowerCase().includes(q) || entry.keywords.some((k) => k.toLowerCase().includes(q))
    if (matches) {
      seen.add(emoji)
      results.push(emoji)
    }
  }
  return results
}

export function EmojiPicker({ onPick, onClose, placement = 'below', align = 'left' }: EmojiPickerProps) {
  useEscapeKey(onClose)
  const [query, setQuery] = useState('')
  const searchResults = useMemo(() => searchEmoji(query), [query])
  const searching = query.trim().length > 0

  return (
    <>
      <div className="emoji-picker-scrim" onClick={onClose} />
      <div
        className={`emoji-picker emoji-picker-${placement} emoji-picker-${align}`}
        role="menu"
      >
        <input
          type="text"
          className="emoji-picker-search"
          placeholder="Search emoji"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        {searching ? (
          searchResults.length > 0 ? (
            <div className="emoji-picker-grid">
              {searchResults.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  role="menuitem"
                  className="emoji-picker-item"
                  title={EMOJI_NAMES[emoji]?.name}
                  onClick={() => onPick(emoji)}
                >
                  {emoji}
                </button>
              ))}
            </div>
          ) : (
            <div className="emoji-picker-no-results">No emoji found</div>
          )
        ) : (
          EMOJI_CATEGORIES.map((category) => (
            <div key={category.label} className="emoji-picker-category">
              <div className="emoji-picker-category-label">{category.label}</div>
              <div className="emoji-picker-grid">
                {category.emoji.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    role="menuitem"
                    className="emoji-picker-item"
                    title={EMOJI_NAMES[emoji]?.name}
                    onClick={() => onPick(emoji)}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </>
  )
}

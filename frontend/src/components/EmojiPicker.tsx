import { useMemo, useState, type MouseEvent } from 'react'
import { deleteCustomEmoji } from '../api/customEmoji'
import { useAuth } from '../context/AuthContext'
import { useCustomEmoji } from '../context/CustomEmojiContext'
import { useEscapeKey } from '../hooks/useEscapeKey'
import { ALL_EMOJI, EMOJI_CATEGORIES } from '../lib/emoji'
import { EMOJI_NAMES } from '../lib/emojiNames'
import { getRecentEmoji, recordEmojiUsed } from '../lib/recentEmoji'
import { CustomEmojiUploadModal } from './CustomEmojiUploadModal'
import { EmojiGlyph } from './MessageContent'
import './EmojiPicker.css'

interface EmojiPickerProps {
  onPick: (emoji: string) => void
  onClose: () => void
  placement?: 'above' | 'below'
  align?: 'left' | 'right'
}

// Kept in sync with .emoji-picker's max-height in EmojiPicker.css -- callers
// that compute placement dynamically (flipping above/below based on
// available viewport space) need this to know how much room to check for.
export const EMOJI_PICKER_MAX_HEIGHT = 380

// Every emoji this picker deals with -- built-in or custom -- is just a
// string from here on: a raw unicode glyph, or a custom emoji's literal
// `:shortcode:` reference (see EmojiGlyph in MessageContent.tsx, which
// resolves either into the right thing to render). Keeping both kinds in
// the same list/search/recent machinery means there's exactly one grid
// rendering path instead of a parallel one for custom emoji.
function titleFor(value: string): string {
  return EMOJI_NAMES[value]?.name ?? value
}

function searchEmoji(query: string, customShortcodes: string[]): string[] {
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
  for (const shortcode of customShortcodes) {
    if (shortcode.toLowerCase().includes(q)) results.push(`:${shortcode}:`)
  }
  return results
}

export function EmojiPicker({ onPick, onClose, placement = 'below', align = 'left' }: EmojiPickerProps) {
  useEscapeKey(onClose)
  const { user } = useAuth()
  const { list: customEmoji, refresh: refreshCustomEmoji } = useCustomEmoji()
  const [query, setQuery] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const customShortcodes = useMemo(() => customEmoji.map((e) => e.shortcode), [customEmoji])
  const searchResults = useMemo(() => searchEmoji(query, customShortcodes), [query, customShortcodes])
  const searching = query.trim().length > 0
  // A snapshot taken once when the picker opens, not live-updating as picks
  // happen within this same session -- picking an emoji always closes the
  // picker (see Composer.tsx/MessageList.tsx), so there's never a second
  // pick in the same open session to show an updated list to.
  const [recent] = useState(getRecentEmoji)

  function pick(emoji: string) {
    recordEmojiUsed(emoji)
    onPick(emoji)
  }

  async function handleDeleteCustomEmoji(e: MouseEvent, emojiId: string) {
    // Delete, not pick -- must never bubble to the button's own onClick.
    e.stopPropagation()
    setDeletingId(emojiId)
    try {
      await deleteCustomEmoji(emojiId)
      await refreshCustomEmoji()
    } finally {
      setDeletingId(null)
    }
  }

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
                  title={titleFor(emoji)}
                  onClick={() => pick(emoji)}
                >
                  <EmojiGlyph value={emoji} />
                </button>
              ))}
            </div>
          ) : (
            <div className="emoji-picker-no-results">No emoji found</div>
          )
        ) : (
          <>
            <div className="emoji-picker-category">
              <div className="emoji-picker-category-label-row">
                <div className="emoji-picker-category-label">Custom</div>
                <button
                  type="button"
                  className="emoji-picker-add-custom"
                  onClick={() => setUploadOpen(true)}
                >
                  + Add
                </button>
              </div>
              {customEmoji.length > 0 && (
                <div className="emoji-picker-grid">
                  {customEmoji.map((e) => {
                    const canDelete = user?.id === e.uploaded_by || user?.is_site_admin
                    return (
                      <button
                        key={e.id}
                        type="button"
                        role="menuitem"
                        className="emoji-picker-item emoji-picker-item-custom"
                        title={`:${e.shortcode}:`}
                        onClick={() => pick(`:${e.shortcode}:`)}
                      >
                        <EmojiGlyph value={`:${e.shortcode}:`} />
                        {canDelete && (
                          <span
                            role="button"
                            aria-label={`Remove :${e.shortcode}:`}
                            className="emoji-picker-item-remove"
                            onClick={(ev) => handleDeleteCustomEmoji(ev, e.id)}
                            style={deletingId === e.id ? { opacity: 0.5, pointerEvents: 'none' } : undefined}
                          >
                            ×
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
            {recent.length > 0 && (
              <div className="emoji-picker-category">
                <div className="emoji-picker-category-label">Recently used</div>
                <div className="emoji-picker-grid">
                  {recent.map((emoji) => (
                    <button
                      key={emoji}
                      type="button"
                      role="menuitem"
                      className="emoji-picker-item"
                      title={titleFor(emoji)}
                      onClick={() => pick(emoji)}
                    >
                      <EmojiGlyph value={emoji} />
                    </button>
                  ))}
                </div>
              </div>
            )}
            {EMOJI_CATEGORIES.map((category) => (
              <div key={category.label} className="emoji-picker-category">
                <div className="emoji-picker-category-label">{category.label}</div>
                <div className="emoji-picker-grid">
                  {category.emoji.map((emoji) => (
                    <button
                      key={emoji}
                      type="button"
                      role="menuitem"
                      className="emoji-picker-item"
                      title={titleFor(emoji)}
                      onClick={() => pick(emoji)}
                    >
                      <EmojiGlyph value={emoji} />
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
      {uploadOpen && (
        <CustomEmojiUploadModal
          onClose={() => setUploadOpen(false)}
          onUploaded={() => {
            refreshCustomEmoji()
            setUploadOpen(false)
          }}
        />
      )}
    </>
  )
}

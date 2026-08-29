import { getCustomEmojiUrl } from '../api/customEmoji'
import './ComposerAutocomplete.css'

export interface EmojiShortcodeMatch {
  shortcode: string
  // null for a custom emoji -- there's no unicode glyph to show, so the
  // row renders its uploaded image instead (see getCustomEmojiUrl below).
  glyph: string | null
}

interface EmojiShortcodeAutocompleteProps {
  matches: EmojiShortcodeMatch[]
  activeIndex: number
  onPick: (shortcode: string) => void
  onHover: (index: number) => void
}

export function EmojiShortcodeAutocomplete({
  matches,
  activeIndex,
  onPick,
  onHover,
}: EmojiShortcodeAutocompleteProps) {
  return (
    <div className="composer-autocomplete" role="listbox">
      {matches.map((match, i) => (
        <button
          key={match.shortcode}
          type="button"
          role="option"
          aria-selected={i === activeIndex}
          className={`composer-autocomplete-item${i === activeIndex ? ' composer-autocomplete-item-active' : ''}`}
          // Selecting must survive the textarea's blur (which would
          // otherwise fire first and could dismiss the dropdown) --
          // onMouseDown fires before blur, onClick fires after.
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onPick(match.shortcode)}
          onMouseEnter={() => onHover(i)}
        >
          <span className="composer-autocomplete-emoji-glyph">
            {match.glyph ?? (
              <img
                src={getCustomEmojiUrl(match.shortcode)}
                alt=""
                className="composer-autocomplete-custom-emoji"
              />
            )}
          </span>
          <span className="composer-autocomplete-primary">:{match.shortcode}:</span>
        </button>
      ))}
    </div>
  )
}

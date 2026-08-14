import { useEscapeKey } from '../hooks/useEscapeKey'
import { EMOJI_CATEGORIES } from '../lib/emoji'
import './EmojiPicker.css'

interface EmojiPickerProps {
  onPick: (emoji: string) => void
  onClose: () => void
  placement?: 'above' | 'below'
  align?: 'left' | 'right'
}

export function EmojiPicker({ onPick, onClose, placement = 'below', align = 'left' }: EmojiPickerProps) {
  useEscapeKey(onClose)

  return (
    <>
      <div className="emoji-picker-scrim" onClick={onClose} />
      <div
        className={`emoji-picker emoji-picker-${placement} emoji-picker-${align}`}
        role="menu"
      >
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
                  onClick={() => onPick(emoji)}
                >
                  {emoji}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

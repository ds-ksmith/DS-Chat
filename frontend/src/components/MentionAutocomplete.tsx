import type { RoomMember } from '../types'
import './ComposerAutocomplete.css'

interface MentionAutocompleteProps {
  matches: RoomMember[]
  activeIndex: number
  onPick: (username: string) => void
  onHover: (index: number) => void
}

export function MentionAutocomplete({ matches, activeIndex, onPick, onHover }: MentionAutocompleteProps) {
  return (
    <div className="composer-autocomplete" role="listbox">
      {matches.map((member, i) => (
        <button
          key={member.user_id}
          type="button"
          role="option"
          aria-selected={i === activeIndex}
          className={`composer-autocomplete-item${i === activeIndex ? ' composer-autocomplete-item-active' : ''}`}
          // Selecting must survive the textarea's blur (which would
          // otherwise fire first and could dismiss the dropdown) --
          // onMouseDown fires before blur, onClick fires after.
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onPick(member.username)}
          onMouseEnter={() => onHover(i)}
        >
          <span className="composer-autocomplete-primary">@{member.username}</span>
          {member.display_name && (
            <span className="composer-autocomplete-secondary">{member.display_name}</span>
          )}
        </button>
      ))}
    </div>
  )
}

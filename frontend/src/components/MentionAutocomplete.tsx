import type { RoomMember } from '../types'
import './MentionAutocomplete.css'

interface MentionAutocompleteProps {
  matches: RoomMember[]
  activeIndex: number
  onPick: (username: string) => void
  onHover: (index: number) => void
}

export function MentionAutocomplete({ matches, activeIndex, onPick, onHover }: MentionAutocompleteProps) {
  return (
    <div className="mention-autocomplete" role="listbox">
      {matches.map((member, i) => (
        <button
          key={member.user_id}
          type="button"
          role="option"
          aria-selected={i === activeIndex}
          className={`mention-autocomplete-item${i === activeIndex ? ' mention-autocomplete-item-active' : ''}`}
          // Selecting must survive the textarea's blur (which would
          // otherwise fire first and could dismiss the dropdown) --
          // onMouseDown fires before blur, onClick fires after.
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onPick(member.username)}
          onMouseEnter={() => onHover(i)}
        >
          <span className="mention-autocomplete-username">@{member.username}</span>
          {member.display_name && (
            <span className="mention-autocomplete-display-name">{member.display_name}</span>
          )}
        </button>
      ))}
    </div>
  )
}

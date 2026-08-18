import type { MyRoomItem } from '../types'
import './ComposerAutocomplete.css'

interface RoomReferenceAutocompleteProps {
  matches: MyRoomItem[]
  activeIndex: number
  onPick: (roomName: string) => void
  onHover: (index: number) => void
}

export function RoomReferenceAutocomplete({
  matches,
  activeIndex,
  onPick,
  onHover,
}: RoomReferenceAutocompleteProps) {
  return (
    <div className="composer-autocomplete" role="listbox">
      {matches.map((room, i) => (
        <button
          key={room.id}
          type="button"
          role="option"
          aria-selected={i === activeIndex}
          className={`composer-autocomplete-item${i === activeIndex ? ' composer-autocomplete-item-active' : ''}`}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onPick(room.name)}
          onMouseEnter={() => onHover(i)}
        >
          <span className="composer-autocomplete-primary">#{room.name}</span>
          {room.description && <span className="composer-autocomplete-secondary">{room.description}</span>}
        </button>
      ))}
    </div>
  )
}

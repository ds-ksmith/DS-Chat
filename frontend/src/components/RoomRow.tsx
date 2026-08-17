import { Link } from 'react-router-dom'
import type { MyRoomItem } from '../types'
import { RoomAvatar } from './RoomAvatar'
import './RoomRow.css'

interface RoomRowProps {
  room: MyRoomItem
  colorIndex: number
  active: boolean
}

export function RoomRow({ room, colorIndex, active }: RoomRowProps) {
  return (
    <Link to={`/rooms/${room.id}`} className={`room-row${active ? ' room-row-active' : ''}`}>
      <RoomAvatar colorIndex={colorIndex} />
      <div className="room-row-body">
        <div className="room-row-name">
          {room.name}
          {room.is_private && (
            <svg
              className="room-row-lock"
              width="12"
              height="12"
              viewBox="0 0 20 20"
              fill="none"
              aria-label="Private room"
            >
              <rect x="4" y="9" width="12" height="8" rx="2" stroke="currentColor" strokeWidth="1.6" />
              <path d="M7 9V6.5a3 3 0 0 1 6 0V9" stroke="currentColor" strokeWidth="1.6" />
            </svg>
          )}
        </div>
        {room.description && <div className="room-row-subtitle">{room.description}</div>}
      </div>
      {room.has_unread && !active && <span className="room-row-unread-dot" aria-label="Unread messages" />}
    </Link>
  )
}

import { Link } from 'react-router-dom'
import { getUserAvatarUrl } from '../api/users'
import { hashIndex } from '../lib/avatar'
import type { MyRoomItem } from '../types'
import { RoomAvatar } from './RoomAvatar'
import { UserAvatar } from './UserAvatar'
import './RoomRow.css'

interface RoomRowProps {
  room: MyRoomItem
  colorIndex: number
  active: boolean
}

export function RoomRow({ room, colorIndex, active }: RoomRowProps) {
  const partner = room.dm_partner

  return (
    <Link to={`/rooms/${room.id}`} className={`room-row${active ? ' room-row-active' : ''}`}>
      {partner ? (
        <UserAvatar
          username={partner.username}
          colorIndex={hashIndex(partner.username)}
          size={34}
          avatarUrl={partner.avatar_filename ? getUserAvatarUrl(partner.user_id, partner.avatar_filename) : null}
          status={partner.status}
        />
      ) : (
        <RoomAvatar colorIndex={colorIndex} />
      )}
      <div className="room-row-body">
        <div className="room-row-name">
          {partner ? partner.display_name || partner.username : room.name}
          {!partner && room.is_private && (
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
        {!partner && room.description && <div className="room-row-subtitle">{room.description}</div>}
      </div>
      {!active && room.has_mention && (
        <span className="room-row-mention-dot" aria-label="You were mentioned" />
      )}
      {!active && !room.has_mention && room.has_unread && (
        <span className="room-row-unread-dot" aria-label="Unread messages" />
      )}
    </Link>
  )
}

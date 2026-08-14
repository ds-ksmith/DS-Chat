import { Link } from 'react-router-dom'
import type { RoomListItem as RoomListItemType } from '../types'

interface RoomListItemProps {
  room: RoomListItemType
  onJoin: (roomId: string) => void
  joining: boolean
}

export function RoomListItem({ room, onJoin, joining }: RoomListItemProps) {
  return (
    <li style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.5rem 0' }}>
      <div style={{ flex: 1 }}>
        <strong>{room.name}</strong>
        {room.description && <div style={{ color: '#666' }}>{room.description}</div>}
      </div>
      {room.is_member ? (
        <Link to={`/rooms/${room.id}`}>Open</Link>
      ) : (
        <button disabled={joining} onClick={() => onJoin(room.id)}>
          Join
        </button>
      )}
    </li>
  )
}

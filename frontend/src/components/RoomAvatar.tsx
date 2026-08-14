import { accentForIndex } from '../lib/avatar'
import './RoomAvatar.css'

interface RoomAvatarProps {
  colorIndex: number
  size?: number
}

export function RoomAvatar({ colorIndex, size = 34 }: RoomAvatarProps) {
  return (
    <div
      className="room-avatar"
      style={{ width: size, height: size, background: accentForIndex(colorIndex) }}
    >
      #
    </div>
  )
}

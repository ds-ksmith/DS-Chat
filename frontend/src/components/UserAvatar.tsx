import { accentForIndex, initials } from '../lib/avatar'
import './UserAvatar.css'

interface UserAvatarProps {
  username: string
  colorIndex: number
  size?: number
}

export function UserAvatar({ username, colorIndex, size = 28 }: UserAvatarProps) {
  return (
    <div
      className="user-avatar"
      style={{ width: size, height: size, background: accentForIndex(colorIndex) }}
    >
      {initials(username)}
    </div>
  )
}

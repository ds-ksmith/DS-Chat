import { accentForIndex, initials } from '../lib/avatar'
import './UserAvatar.css'

interface UserAvatarProps {
  username: string
  colorIndex: number
  size?: number
  avatarUrl?: string | null
}

export function UserAvatar({ username, colorIndex, size = 28, avatarUrl }: UserAvatarProps) {
  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt=""
        className="user-avatar user-avatar-img"
        style={{ width: size, height: size }}
      />
    )
  }

  return (
    <div
      className="user-avatar"
      style={{ width: size, height: size, background: accentForIndex(colorIndex) }}
    >
      {initials(username)}
    </div>
  )
}

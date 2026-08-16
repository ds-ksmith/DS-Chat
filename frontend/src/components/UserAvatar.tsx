import { accentForIndex, initials } from '../lib/avatar'
import './UserAvatar.css'

interface UserAvatarProps {
  username: string
  colorIndex: number
  size?: number
  avatarUrl?: string | null
  // undefined -- no presence data for this context (e.g. a bot), don't
  // render a dot at all, rather than guessing.
  status?: 'online' | 'offline'
}

export function UserAvatar({ username, colorIndex, size = 28, avatarUrl, status }: UserAvatarProps) {
  const dotSize = Math.max(8, Math.round(size * 0.32))
  const dot = status && (
    <span
      className={`user-avatar-status-dot user-avatar-status-dot-${status}`}
      style={{ width: dotSize, height: dotSize }}
      aria-label={status === 'online' ? 'Online' : 'Offline'}
      title={status === 'online' ? 'Online' : 'Offline'}
    />
  )

  if (avatarUrl) {
    return (
      <span className="user-avatar-wrap" style={{ width: size, height: size }}>
        <img
          src={avatarUrl}
          alt=""
          className="user-avatar user-avatar-img"
          style={{ width: size, height: size }}
        />
        {dot}
      </span>
    )
  }

  return (
    <span className="user-avatar-wrap" style={{ width: size, height: size }}>
      <div
        className="user-avatar"
        style={{ width: size, height: size, background: accentForIndex(colorIndex) }}
      >
        {initials(username)}
      </div>
      {dot}
    </span>
  )
}

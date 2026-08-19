import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '../api/client'
import { startDm } from '../api/rooms'
import { getUserAvatarUrl, listOnlineUserIds, listUserDirectory } from '../api/users'
import { useAuth } from '../context/AuthContext'
import { hashIndex } from '../lib/avatar'
import type { UserDirectoryEntry } from '../types'
import { UserAvatar } from './UserAvatar'
import './Modal.css'

interface PeopleModalProps {
  onClose: () => void
  onOpenRoom: (roomId: string) => void
}

// #25: a snapshot on open, not a live feed -- matches listOnlineUserIds'
// own documented contract (also used as-is by the admin user list and the
// room-invite search), rather than inventing a new live-updating design
// for this first pass.
export function PeopleModal({ onClose, onOpenRoom }: PeopleModalProps) {
  const { user } = useAuth()
  const [users, setUsers] = useState<UserDirectoryEntry[]>([])
  const [onlineIds, setOnlineIds] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [startingId, setStartingId] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([listUserDirectory(), listOnlineUserIds()])
      .then(([directory, online]) => {
        setUsers(directory)
        setOnlineIds(new Set(online))
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [])

  // Online first (each group alphabetical, matching listUserDirectory's own
  // username ordering) -- who's actually around right now is the more
  // useful thing to see first in a list that can otherwise run to the
  // entire site's user base. Excludes the viewer themselves -- there's no
  // "DM yourself" affordance.
  const sorted = useMemo(
    () =>
      [...users]
        .filter((u) => u.id !== user?.id)
        .sort((a, b) => {
          const aOnline = onlineIds.has(a.id)
          const bOnline = onlineIds.has(b.id)
          if (aOnline !== bOnline) return aOnline ? -1 : 1
          return a.username.localeCompare(b.username)
        }),
    [users, onlineIds, user?.id],
  )

  async function handleStartDm(otherUserId: string) {
    setStartingId(otherUserId)
    setError(null)
    try {
      const room = await startDm(otherUserId)
      onOpenRoom(room.id)
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setStartingId(null)
    }
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>People</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        {error && <p className="modal-error">{error}</p>}

        {loading ? (
          <p className="modal-empty">Loading...</p>
        ) : sorted.length === 0 ? (
          <p className="modal-empty">No users found.</p>
        ) : (
          sorted.map((u) => {
            const online = onlineIds.has(u.id)
            return (
              <button
                key={u.id}
                type="button"
                className="modal-list-row modal-list-row-button"
                onClick={() => handleStartDm(u.id)}
                disabled={startingId !== null}
              >
                <UserAvatar
                  username={u.username}
                  colorIndex={hashIndex(u.username)}
                  size={30}
                  avatarUrl={u.avatar_filename ? getUserAvatarUrl(u.id, u.avatar_filename) : null}
                  status={online ? 'online' : 'offline'}
                />
                <div className="modal-list-row-body">
                  <div className="modal-list-row-title">{u.display_name || u.username}</div>
                  <div className="modal-list-row-sub">
                    {startingId === u.id ? 'Opening…' : online ? 'Online' : 'Offline'}
                  </div>
                </div>
              </button>
            )
          })
        )}

        <div className="modal-actions" style={{ marginTop: '1rem' }}>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

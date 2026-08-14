import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { joinRoom, listRooms } from '../api/rooms'
import type { RoomListItem } from '../types'
import { RoomAvatar } from './RoomAvatar'
import './Modal.css'

interface BrowseRoomsModalProps {
  onClose: () => void
  onJoined: (roomId: string) => void
}

export function BrowseRoomsModal({ onClose, onJoined }: BrowseRoomsModalProps) {
  const [rooms, setRooms] = useState<RoomListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [joiningId, setJoiningId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listRooms()
      .then(setRooms)
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [])

  async function handleJoin(roomId: string) {
    setJoiningId(roomId)
    setError(null)
    try {
      await joinRoom(roomId)
      onJoined(roomId)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setJoiningId(null)
    }
  }

  const joinable = rooms.filter((r) => !r.is_member)

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Browse open rooms</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        {error && <p className="modal-error">{error}</p>}

        {loading ? (
          <p className="modal-empty">Loading...</p>
        ) : joinable.length === 0 ? (
          <p className="modal-empty">No open rooms to join right now.</p>
        ) : (
          joinable.map((room, i) => (
            <div key={room.id} className="modal-list-row">
              <RoomAvatar colorIndex={i} size={30} />
              <div className="modal-list-row-body">
                <div className="modal-list-row-title">{room.name}</div>
                {room.description && <div className="modal-list-row-sub">{room.description}</div>}
              </div>
              <button
                type="button"
                className="btn-secondary"
                disabled={joiningId === room.id}
                onClick={() => handleJoin(room.id)}
              >
                Join
              </button>
            </div>
          ))
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

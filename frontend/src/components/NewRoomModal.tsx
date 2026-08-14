import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { createRoom } from '../api/rooms'
import './Modal.css'

interface NewRoomModalProps {
  onClose: () => void
  onCreated: (roomId: string) => void
}

export function NewRoomModal({ onClose, onCreated }: NewRoomModalProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [isPrivate, setIsPrivate] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    setSubmitting(true)
    setError(null)
    try {
      const room = await createRoom(trimmed, description.trim(), isPrivate)
      onCreated(room.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>New Conversation</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-field-label">Room name</div>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. networking"
            autoFocus
          />
          <div className="modal-field-label">Description (optional)</div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What's this room for?"
            rows={2}
          />
          <div className="toggle-row">
            <div className="toggle-label">
              <span className="t">Private room</span>
              <span className="d">Joinable by invite only</span>
            </div>
            <label className="switch">
              <input
                type="checkbox"
                checked={isPrivate}
                onChange={(e) => setIsPrivate(e.target.checked)}
              />
              <span className="track" />
            </label>
          </div>
          {error && <p className="modal-error">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={submitting || !name.trim()}>
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { acceptInvite, declineInvite, listMyInvites } from '../api/invites'
import { ApiError } from '../api/client'
import type { MyInvite } from '../types'
import './Modal.css'

interface InvitesModalProps {
  onClose: () => void
  onAccepted: (roomId: string) => void
  onInvitesChanged: (count: number) => void
}

export function InvitesModal({ onClose, onAccepted, onInvitesChanged }: InvitesModalProps) {
  const [invites, setInvites] = useState<MyInvite[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    const list = await listMyInvites()
    setInvites(list)
    onInvitesChanged(list.length)
  }

  useEffect(() => {
    refresh()
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleAccept(invite: MyInvite) {
    setBusyId(invite.id)
    setError(null)
    try {
      await acceptInvite(invite.id)
      await refresh()
      onAccepted(invite.room_id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  async function handleDecline(invite: MyInvite) {
    setBusyId(invite.id)
    setError(null)
    try {
      await declineInvite(invite.id)
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Your invites</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        {error && <p className="modal-error">{error}</p>}

        {loading ? (
          <p className="modal-empty">Loading...</p>
        ) : invites.length === 0 ? (
          <p className="modal-empty">No pending invites.</p>
        ) : (
          invites.map((invite) => (
            <div key={invite.id} className="modal-list-row">
              <div className="modal-list-row-body">
                <div className="modal-list-row-title">{invite.room_name}</div>
                <div className="modal-list-row-sub">Invited by {invite.invited_by_username}</div>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={busyId === invite.id}
                  onClick={() => handleDecline(invite)}
                >
                  Decline
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={busyId === invite.id}
                  onClick={() => handleAccept(invite)}
                >
                  Accept
                </button>
              </div>
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

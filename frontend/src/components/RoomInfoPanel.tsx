import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { createInvite, listRoomInvites, revokeInvite } from '../api/invites'
import {
  changeMemberRole,
  deleteRoom,
  leaveRoom,
  removeMember,
  transferOwnership,
  updateRoom,
} from '../api/rooms'
import { useAuth } from '../context/AuthContext'
import type { Invite, MyRoomItem, RoomMember, RoomRole } from '../types'
import { RoomAvatar } from './RoomAvatar'
import { UserAvatar } from './UserAvatar'
import './RoomInfoPanel.css'

interface RoomInfoPanelProps {
  room: MyRoomItem
  members: RoomMember[]
  onClose: () => void
  onMembersChanged: () => void
  onRoomUpdated: () => void
  onRoomDeleted: () => void
  onLeft: () => void
}

export function RoomInfoPanel({
  room,
  members,
  onClose,
  onMembersChanged,
  onRoomUpdated,
  onRoomDeleted,
  onLeft,
}: RoomInfoPanelProps) {
  const { user } = useAuth()
  const myRole = room.role

  const [inviteUsername, setInviteUsername] = useState('')
  const [inviteError, setInviteError] = useState<string | null>(null)
  const [pendingInvites, setPendingInvites] = useState<Invite[]>([])
  const [busyUserId, setBusyUserId] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [nameDraft, setNameDraft] = useState(room.name)
  const [descDraft, setDescDraft] = useState(room.description ?? '')
  const [roomError, setRoomError] = useState<string | null>(null)

  const canManage = myRole === 'admin' || myRole === 'owner'

  useEffect(() => {
    setNameDraft(room.name)
    setDescDraft(room.description ?? '')
    if (canManage) {
      listRoomInvites(room.id).then(setPendingInvites).catch(() => setPendingInvites([]))
    } else {
      setPendingInvites([])
    }
  }, [room.id, room.name, room.description, canManage])

  async function handleInvite(e: FormEvent) {
    e.preventDefault()
    const username = inviteUsername.trim()
    if (!username) return
    setInviteError(null)
    try {
      await createInvite(room.id, username)
      setInviteUsername('')
      setPendingInvites(await listRoomInvites(room.id))
    } catch (err) {
      setInviteError(err instanceof ApiError ? err.message : String(err))
    }
  }

  async function handleRevoke(inviteId: string) {
    await revokeInvite(room.id, inviteId)
    setPendingInvites(await listRoomInvites(room.id))
  }

  async function handleRemove(userId: string) {
    setBusyUserId(userId)
    try {
      await removeMember(room.id, userId)
      onMembersChanged()
    } finally {
      setBusyUserId(null)
    }
  }

  async function handleRoleChange(userId: string, role: RoomRole) {
    setBusyUserId(userId)
    try {
      await changeMemberRole(room.id, userId, role)
      onMembersChanged()
    } finally {
      setBusyUserId(null)
    }
  }

  async function handleTransfer(userId: string) {
    if (!confirm('Transfer ownership to this member? You will become an admin.')) return
    setBusyUserId(userId)
    try {
      await transferOwnership(room.id, userId)
      onMembersChanged()
      onRoomUpdated()
    } finally {
      setBusyUserId(null)
    }
  }

  async function handleLeave() {
    if (myRole === 'owner') return
    if (!confirm(`Leave #${room.name}?`)) return
    await leaveRoom(room.id)
    onLeft()
  }

  async function handleSaveSettings(e: FormEvent) {
    e.preventDefault()
    setRoomError(null)
    try {
      await updateRoom(room.id, { name: nameDraft.trim(), description: descDraft.trim() })
      onRoomUpdated()
    } catch (err) {
      setRoomError(err instanceof ApiError ? err.message : String(err))
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete #${room.name}? This removes all messages and can't be undone.`)) return
    await deleteRoom(room.id)
    onRoomDeleted()
  }

  return (
    <aside className="room-info-panel">
      <div className="room-info-header">
        <span className="room-info-header-label">Details</span>
        <button type="button" className="room-info-close" onClick={onClose} aria-label="Close">
          &times;
        </button>
      </div>

      <div className="room-info-summary">
        <RoomAvatar colorIndex={0} size={56} />
        <div className="room-info-name">#{room.name}</div>
        <div className="room-info-sub">
          {members.length} member{members.length === 1 ? '' : 's'}
          {room.is_private && ' · Private'}
        </div>
      </div>

      <div className="room-info-section">
        <div className="room-info-label">Members</div>
        {members.map((m, i) => (
          <div key={m.user_id} className="room-info-member-row">
            <UserAvatar username={m.username} colorIndex={i} size={24} />
            <span className="room-info-member-name">{m.username}</span>
            <span className={`role-badge role-badge-${m.role}`}>{m.role}</span>
            {myRole === 'owner' && m.user_id !== user?.id && (
              <div className="room-info-member-actions">
                {m.role === 'member' && (
                  <button
                    type="button"
                    disabled={busyUserId === m.user_id}
                    onClick={() => handleRoleChange(m.user_id, 'admin')}
                    title="Promote to admin"
                  >
                    Promote
                  </button>
                )}
                {m.role === 'admin' && (
                  <button
                    type="button"
                    disabled={busyUserId === m.user_id}
                    onClick={() => handleRoleChange(m.user_id, 'member')}
                    title="Demote to member"
                  >
                    Demote
                  </button>
                )}
                <button
                  type="button"
                  disabled={busyUserId === m.user_id}
                  onClick={() => handleTransfer(m.user_id)}
                  title="Transfer ownership"
                >
                  Make owner
                </button>
                <button
                  type="button"
                  className="room-info-danger-link"
                  disabled={busyUserId === m.user_id}
                  onClick={() => handleRemove(m.user_id)}
                  title="Remove from room"
                >
                  Remove
                </button>
              </div>
            )}
            {myRole === 'admin' && m.role === 'member' && m.user_id !== user?.id && (
              <div className="room-info-member-actions">
                <button
                  type="button"
                  className="room-info-danger-link"
                  disabled={busyUserId === m.user_id}
                  onClick={() => handleRemove(m.user_id)}
                  title="Remove from room"
                >
                  Remove
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {canManage && (
        <div className="room-info-section">
          <div className="room-info-label">Invite someone</div>
          <form className="room-info-invite-form" onSubmit={handleInvite}>
            <input
              type="text"
              placeholder="Username"
              value={inviteUsername}
              onChange={(e) => setInviteUsername(e.target.value)}
            />
            <button type="submit" className="btn-secondary">
              Invite
            </button>
          </form>
          {inviteError && <p className="room-info-error">{inviteError}</p>}

          {pendingInvites.length > 0 && (
            <div className="room-info-pending">
              {pendingInvites.map((inv) => (
                <div key={inv.id} className="room-info-pending-row">
                  <span>{inv.target_username ?? 'Unknown user'}</span>
                  <button
                    type="button"
                    className="room-info-danger-link"
                    onClick={() => handleRevoke(inv.id)}
                    title="Revoke invite"
                  >
                    Revoke
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {myRole === 'owner' && (
        <div className="room-info-section">
          <button
            type="button"
            className="room-info-settings-toggle"
            onClick={() => setSettingsOpen((v) => !v)}
          >
            Room settings {settingsOpen ? '−' : '+'}
          </button>
          {settingsOpen && (
            <form className="room-info-settings-form" onSubmit={handleSaveSettings}>
              <label>
                Name
                <input value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} />
              </label>
              <label>
                Description
                <textarea value={descDraft} onChange={(e) => setDescDraft(e.target.value)} rows={2} />
              </label>
              {roomError && <p className="room-info-error">{roomError}</p>}
              <button type="submit" className="btn-secondary">
                Save
              </button>
              <button type="button" className="room-info-danger-link" onClick={handleDelete}>
                Delete room
              </button>
            </form>
          )}
        </div>
      )}

      <button
        type="button"
        className="room-info-leave"
        onClick={handleLeave}
        disabled={myRole === 'owner'}
        title={myRole === 'owner' ? 'Transfer ownership before leaving' : undefined}
      >
        Leave room
      </button>
    </aside>
  )
}

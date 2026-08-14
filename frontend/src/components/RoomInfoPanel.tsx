import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { createInvite, listRoomInvites, revokeInvite } from '../api/invites'
import { getUserAvatarUrl } from '../api/users'
import {
  changeMemberRole,
  deleteRoom,
  leaveRoom,
  removeMember,
  transferOwnership,
  updateRoom,
} from '../api/rooms'
import {
  createEventSubscription,
  createIncomingWebhook,
  listEventSubscriptions,
  listIncomingWebhooks,
  revokeEventSubscription,
  revokeIncomingWebhook,
} from '../api/webhooks'
import { useAuth } from '../context/AuthContext'
import type {
  EventSubscription,
  EventType,
  Invite,
  MyRoomItem,
  RoomMember,
  RoomRole,
  WebhookIncoming,
} from '../types'
import { RoomAvatar } from './RoomAvatar'
import { UserAvatar } from './UserAvatar'
import './RoomInfoPanel.css'

const EVENT_TYPES: EventType[] = ['message.created', 'message.updated']

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

  const [integrationsOpen, setIntegrationsOpen] = useState(false)
  const [incomingWebhooks, setIncomingWebhooks] = useState<WebhookIncoming[]>([])
  const [webhookDescription, setWebhookDescription] = useState('')
  const [eventSubscriptions, setEventSubscriptions] = useState<EventSubscription[]>([])
  const [targetUrl, setTargetUrl] = useState('')
  const [selectedEventTypes, setSelectedEventTypes] = useState<EventType[]>([])
  const [newSigningSecret, setNewSigningSecret] = useState<string | null>(null)
  const [integrationsError, setIntegrationsError] = useState<string | null>(null)

  const canManage = myRole === 'admin' || myRole === 'owner'

  useEffect(() => {
    setNameDraft(room.name)
    setDescDraft(room.description ?? '')
    if (canManage) {
      listRoomInvites(room.id).then(setPendingInvites).catch(() => setPendingInvites([]))
      listIncomingWebhooks(room.id).then(setIncomingWebhooks).catch(() => setIncomingWebhooks([]))
      listEventSubscriptions(room.id).then(setEventSubscriptions).catch(() => setEventSubscriptions([]))
    } else {
      setPendingInvites([])
      setIncomingWebhooks([])
      setEventSubscriptions([])
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

  async function handleCreateWebhook(e: FormEvent) {
    e.preventDefault()
    setIntegrationsError(null)
    try {
      await createIncomingWebhook(room.id, webhookDescription.trim())
      setWebhookDescription('')
      setIncomingWebhooks(await listIncomingWebhooks(room.id))
    } catch (err) {
      setIntegrationsError(err instanceof ApiError ? err.message : String(err))
    }
  }

  async function handleRevokeWebhook(webhookId: string) {
    await revokeIncomingWebhook(room.id, webhookId)
    setIncomingWebhooks(await listIncomingWebhooks(room.id))
  }

  function toggleEventType(eventType: EventType) {
    setSelectedEventTypes((prev) =>
      prev.includes(eventType) ? prev.filter((t) => t !== eventType) : [...prev, eventType],
    )
  }

  async function handleCreateSubscription(e: FormEvent) {
    e.preventDefault()
    setIntegrationsError(null)
    const url = targetUrl.trim()
    if (!url || selectedEventTypes.length === 0) return
    try {
      const created = await createEventSubscription(room.id, selectedEventTypes, url)
      setNewSigningSecret(created.signing_secret)
      setTargetUrl('')
      setSelectedEventTypes([])
      setEventSubscriptions(await listEventSubscriptions(room.id))
    } catch (err) {
      setIntegrationsError(err instanceof ApiError ? err.message : String(err))
    }
  }

  async function handleRevokeSubscription(subscriptionId: string) {
    await revokeEventSubscription(room.id, subscriptionId)
    setEventSubscriptions(await listEventSubscriptions(room.id))
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
            <UserAvatar
              username={m.username}
              colorIndex={i}
              size={24}
              avatarUrl={m.avatar_filename ? getUserAvatarUrl(m.user_id, m.avatar_filename) : null}
            />
            <span className="room-info-member-name">{m.display_name || m.username}</span>
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

      {canManage && (
        <div className="room-info-section">
          <button
            type="button"
            className="room-info-settings-toggle"
            onClick={() => setIntegrationsOpen((v) => !v)}
          >
            Integrations {integrationsOpen ? '−' : '+'}
          </button>
          {integrationsOpen && (
            <div className="room-info-integrations">
              {integrationsError && <p className="room-info-error">{integrationsError}</p>}

              <div className="room-info-integration-group">
                <div className="room-info-label">Incoming webhooks</div>
                {incomingWebhooks.map((w) => (
                  <div key={w.id} className="room-info-webhook-row">
                    <div className="room-info-webhook-info">
                      <code>{`${window.location.origin}/api/webhooks/incoming/${w.token}`}</code>
                      {w.description && <span className="room-info-webhook-desc">{w.description}</span>}
                    </div>
                    <button
                      type="button"
                      className="room-info-danger-link"
                      onClick={() => handleRevokeWebhook(w.id)}
                    >
                      Revoke
                    </button>
                  </div>
                ))}
                <form className="room-info-invite-form" onSubmit={handleCreateWebhook}>
                  <input
                    type="text"
                    placeholder="Description (optional)"
                    value={webhookDescription}
                    onChange={(e) => setWebhookDescription(e.target.value)}
                  />
                  <button type="submit" className="btn-secondary">
                    Add
                  </button>
                </form>
              </div>

              <div className="room-info-integration-group">
                <div className="room-info-label">Outgoing event subscriptions</div>
                {eventSubscriptions.map((s) => (
                  <div key={s.id} className="room-info-webhook-row">
                    <div className="room-info-webhook-info">
                      <code>{s.target_url}</code>
                      <span className="room-info-webhook-desc">{s.event_types.join(', ')}</span>
                    </div>
                    <button
                      type="button"
                      className="room-info-danger-link"
                      onClick={() => handleRevokeSubscription(s.id)}
                    >
                      Revoke
                    </button>
                  </div>
                ))}
                <form className="room-info-subscription-form" onSubmit={handleCreateSubscription}>
                  <input
                    type="text"
                    placeholder="https://example.com/hook"
                    value={targetUrl}
                    onChange={(e) => setTargetUrl(e.target.value)}
                  />
                  <div className="room-info-event-types">
                    {EVENT_TYPES.map((eventType) => (
                      <label key={eventType} className="room-info-event-type-checkbox">
                        <input
                          type="checkbox"
                          checked={selectedEventTypes.includes(eventType)}
                          onChange={() => toggleEventType(eventType)}
                        />
                        {eventType}
                      </label>
                    ))}
                  </div>
                  <button
                    type="submit"
                    className="btn-secondary"
                    disabled={!targetUrl.trim() || selectedEventTypes.length === 0}
                  >
                    Add
                  </button>
                </form>
                {newSigningSecret && (
                  <p className="room-info-signing-secret">
                    New signing secret (copy it now, it won't be shown again):{' '}
                    <code>{newSigningSecret}</code>
                  </p>
                )}
              </div>
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

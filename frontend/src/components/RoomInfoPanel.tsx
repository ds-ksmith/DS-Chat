import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { getUserAvatarUrl, listUserDirectory } from '../api/users'
import {
  addRoomMember,
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
import { useResizableWidth } from '../hooks/useResizableWidth'
import { MOBILE_BREAKPOINT, useWindowWidth } from '../hooks/useWindowWidth'
import type {
  EventSubscription,
  EventType,
  MyRoomItem,
  RoomMember,
  RoomRole,
  UserDirectoryEntry,
  WebhookIncoming,
} from '../types'
import { RoomAvatar } from './RoomAvatar'
import { UserAvatar } from './UserAvatar'
import { UserPicker } from './UserPicker'
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
  const windowWidth = useWindowWidth()
  const isMobile = windowWidth < MOBILE_BREAKPOINT
  const { width, startResize } = useResizableWidth({
    storageKey: 'room-info-panel-width',
    defaultWidth: 260,
    min: 260,
    max: 480,
  })

  const [inviteError, setInviteError] = useState<string | null>(null)
  const [directoryUsers, setDirectoryUsers] = useState<UserDirectoryEntry[]>([])
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
      listIncomingWebhooks(room.id).then(setIncomingWebhooks).catch(() => setIncomingWebhooks([]))
      listEventSubscriptions(room.id).then(setEventSubscriptions).catch(() => setEventSubscriptions([]))
      listUserDirectory().then(setDirectoryUsers).catch(() => setDirectoryUsers([]))
    } else {
      setIncomingWebhooks([])
      setEventSubscriptions([])
      setDirectoryUsers([])
    }
  }, [room.id, room.name, room.description, canManage])

  async function handleAddMember(target: UserDirectoryEntry) {
    setInviteError(null)
    try {
      await addRoomMember(room.id, target.id)
      onMembersChanged()
    } catch (err) {
      setInviteError(err instanceof ApiError ? err.message : String(err))
    }
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

  function memberActions(m: RoomMember): { value: string; label: string }[] {
    if (m.user_id === user?.id) return []
    if (myRole === 'owner') {
      const actions: { value: string; label: string }[] = []
      if (m.role === 'member') actions.push({ value: 'promote', label: 'Promote to admin' })
      if (m.role === 'admin') actions.push({ value: 'demote', label: 'Demote to member' })
      actions.push({ value: 'transfer', label: 'Make owner' })
      actions.push({ value: 'remove', label: 'Remove from room' })
      return actions
    }
    if (myRole === 'admin' && m.role === 'member') {
      return [{ value: 'remove', label: 'Remove from room' }]
    }
    return []
  }

  function handleMemberAction(userId: string, action: string) {
    if (action === 'promote') handleRoleChange(userId, 'admin')
    else if (action === 'demote') handleRoleChange(userId, 'member')
    else if (action === 'transfer') handleTransfer(userId)
    else if (action === 'remove') handleRemove(userId)
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
    <aside className="room-info-panel" style={isMobile ? undefined : { width }}>
      {!isMobile && <div className="room-info-resize-handle" onPointerDown={startResize} />}
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
        {members.map((m, i) => {
          const actions = memberActions(m)
          return (
            <div key={m.user_id} className="room-info-member-row">
              <UserAvatar
                username={m.username}
                colorIndex={i}
                size={24}
                avatarUrl={m.avatar_filename ? getUserAvatarUrl(m.user_id, m.avatar_filename) : null}
                status={m.status}
              />
              <span className="room-info-member-name">{m.display_name || m.username}</span>
              {actions.length > 0 ? (
                <select
                  className={`role-badge role-badge-${m.role} room-info-role-select`}
                  value={m.role}
                  disabled={busyUserId === m.user_id}
                  onChange={(e) => {
                    const action = e.target.value
                    if (action && action !== m.role) handleMemberAction(m.user_id, action)
                  }}
                  aria-label={`Role and actions for ${m.display_name || m.username}`}
                >
                  <option value={m.role}>{m.role[0].toUpperCase() + m.role.slice(1)}</option>
                  {actions.map((a) => (
                    <option key={a.value} value={a.value}>
                      {a.label}
                    </option>
                  ))}
                </select>
              ) : (
                <span className={`role-badge role-badge-${m.role}`}>{m.role}</span>
              )}
            </div>
          )
        })}
      </div>

      {canManage && (
        <div className="room-info-section">
          <div className="room-info-label">Add someone</div>
          <UserPicker
            users={directoryUsers}
            excludeUserIds={members.map((m) => m.user_id)}
            placeholder="Search users to add…"
            onSelect={handleAddMember}
          />
          {inviteError && <p className="room-info-error">{inviteError}</p>}
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

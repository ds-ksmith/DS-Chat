import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { getUserAvatarUrl, listUserDirectory } from '../api/users'
import {
  addRoomMember,
  changeMemberRole,
  deleteRoom,
  getRoomFileUrl,
  getRoomImageUrl,
  hideDm,
  leaveRoom,
  listRoomAttachments,
  removeMember,
  transferOwnership,
  updateRoom,
  updateRoomNotifications,
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
import { hashIndex } from '../lib/avatar'
import { MOBILE_BREAKPOINT, useWindowWidth } from '../hooks/useWindowWidth'
import { formatFileSize } from '../lib/fileSize'
import type {
  EventSubscription,
  EventType,
  MessageFileInfo,
  MyRoomItem,
  RoomAttachment,
  RoomMember,
  RoomRole,
  UserDirectoryEntry,
  WebhookIncoming,
} from '../types'
import { FilePreviewModal, getPreviewKind } from './FilePreviewModal'
import { ImageLightbox } from './ImageLightbox'
import { FileAttachmentIcon } from './MessageList'
import { RoomAvatar } from './RoomAvatar'
import { UserAvatar } from './UserAvatar'
import { UserPicker } from './UserPicker'
import './Modal.css'
import './RoomInfoPanel.css'

const EVENT_TYPES: EventType[] = ['message.created', 'message.updated']

// Disclosure chevron for the collapsible sections below (Files,
// Integrations, Room settings) -- points right when collapsed, rotates 90°
// clockwise (pointing down) when expanded, same convention as most
// disclosure triangles rather than a +/- glyph.
function DisclosureChevron({ open }: { open: boolean }) {
  return (
    <span className={`room-info-settings-chevron${open ? ' room-info-settings-chevron-open' : ''}`}>
      <svg width="12" height="12" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <polyline points="7,4 13,10 7,16" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  )
}

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
  const [filesOpen, setFilesOpen] = useState(false)
  const [attachments, setAttachments] = useState<RoomAttachment[]>([])
  const [attachmentsError, setAttachmentsError] = useState<string | null>(null)
  const [previewFile, setPreviewFile] = useState<MessageFileInfo | null>(null)
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [nameDraft, setNameDraft] = useState(room.name)
  const [descDraft, setDescDraft] = useState(room.description ?? '')
  const [isPrivateDraft, setIsPrivateDraft] = useState(room.is_private)
  const [roomError, setRoomError] = useState<string | null>(null)
  const [emailNotifications, setEmailNotifications] = useState(room.email_notifications)
  const [notificationsError, setNotificationsError] = useState<string | null>(null)

  const [integrationsOpen, setIntegrationsOpen] = useState(false)
  const [incomingWebhooks, setIncomingWebhooks] = useState<WebhookIncoming[]>([])
  const [webhookDescription, setWebhookDescription] = useState('')
  const [eventSubscriptions, setEventSubscriptions] = useState<EventSubscription[]>([])
  const [targetUrl, setTargetUrl] = useState('')
  const [selectedEventTypes, setSelectedEventTypes] = useState<EventType[]>([])
  const [newSigningSecret, setNewSigningSecret] = useState<string | null>(null)
  const [integrationsError, setIntegrationsError] = useState<string | null>(null)

  const canManage = myRole === 'admin' || myRole === 'owner'
  // #48: room owner, room admin, or site admin (regardless of their role in
  // *this* room) can edit room settings, including privacy -- matches the
  // backend PATCH /api/rooms/{id} gate exactly (see rooms.py). #52: never
  // for a DM regardless of role -- mirrors update_room's own
  // CannotModifyDmError guard, since a DM's `name` is an internal token,
  // not something editable.
  const canEditSettings = !room.is_dm && (canManage || !!user?.is_site_admin)

  useEffect(() => {
    setNameDraft(room.name)
    setDescDraft(room.description ?? '')
    setIsPrivateDraft(room.is_private)
    setEmailNotifications(room.email_notifications)
    if (canManage) {
      listIncomingWebhooks(room.id).then(setIncomingWebhooks).catch(() => setIncomingWebhooks([]))
      listEventSubscriptions(room.id).then(setEventSubscriptions).catch(() => setEventSubscriptions([]))
      listUserDirectory().then(setDirectoryUsers).catch(() => setDirectoryUsers([]))
    } else {
      setIncomingWebhooks([])
      setEventSubscriptions([])
      setDirectoryUsers([])
    }
  }, [room.id, room.name, room.description, room.is_private, room.email_notifications, canManage])

  useEffect(() => {
    // Fetched lazily (only once expanded), not alongside the section above
    // -- unlike webhooks/directory this is visible to every member, not
    // just admins, so eagerly fetching on every room open would add a
    // request most opens never need.
    if (!filesOpen) return
    setAttachmentsError(null)
    listRoomAttachments(room.id)
      .then(setAttachments)
      .catch((err) => setAttachmentsError(err instanceof ApiError ? err.message : String(err)))
  }, [filesOpen, room.id])

  async function handleToggleEmailNotifications(enabled: boolean) {
    const previous = emailNotifications
    setEmailNotifications(enabled)
    setNotificationsError(null)
    try {
      await updateRoomNotifications(room.id, enabled)
      onRoomUpdated()
    } catch (err) {
      setEmailNotifications(previous)
      setNotificationsError(err instanceof ApiError ? err.message : String(err))
    }
  }

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

  async function handleHideDm() {
    const name = room.dm_partner?.display_name || room.dm_partner?.username || 'this conversation'
    if (!confirm(`Hide your conversation with ${name}? It'll come back if either of you sends a new message.`)) {
      return
    }
    await hideDm(room.id)
    onLeft()
  }

  async function handleSaveSettings(e: FormEvent) {
    e.preventDefault()
    setRoomError(null)
    try {
      await updateRoom(room.id, {
        name: nameDraft.trim(),
        description: descDraft.trim(),
        is_private: isPrivateDraft,
      })
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
        {room.dm_partner ? (
          <>
            <UserAvatar
              username={room.dm_partner.username}
              colorIndex={hashIndex(room.dm_partner.username)}
              size={56}
              avatarUrl={
                room.dm_partner.avatar_filename
                  ? getUserAvatarUrl(room.dm_partner.user_id, room.dm_partner.avatar_filename)
                  : null
              }
              status={room.dm_partner.status}
            />
            <div className="room-info-name">{room.dm_partner.display_name || room.dm_partner.username}</div>
            <div className="room-info-sub">{room.dm_partner.status === 'online' ? 'Online' : 'Offline'}</div>
          </>
        ) : (
          <>
            <RoomAvatar colorIndex={0} size={56} />
            <div className="room-info-name">#{room.name}</div>
            <div className="room-info-sub">
              {members.length} member{members.length === 1 ? '' : 's'}
              {room.is_private && ' · Private'}
            </div>
          </>
        )}
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

      {!room.is_dm && (
        <div className="room-info-section">
          <div className="toggle-row">
            <div className="toggle-label">
              <span className="t">Email notifications</span>
              <span className="d">New messages and mentions, while you're offline</span>
            </div>
            <label className="switch">
              <input
                type="checkbox"
                checked={emailNotifications}
                onChange={(e) => handleToggleEmailNotifications(e.target.checked)}
              />
              <span className="track" />
            </label>
          </div>
          {notificationsError && <p className="room-info-error">{notificationsError}</p>}
        </div>
      )}

      <div className="room-info-section">
        <button type="button" className="room-info-settings-toggle" onClick={() => setFilesOpen((v) => !v)}>
          <DisclosureChevron open={filesOpen} /> Files
        </button>
        {filesOpen && (
          <div className="room-info-files">
            {attachmentsError && <p className="room-info-error">{attachmentsError}</p>}
            {!attachmentsError && attachments.length === 0 && (
              <p className="room-info-files-empty">No files or images yet.</p>
            )}
            {attachments.map((a) => {
              const label = a.filename ?? 'Image'
              const meta = `${formatFileSize(a.size_bytes)} · ${a.uploaded_by}`
              const inner = (
                <>
                  <FileAttachmentIcon />
                  <span className="room-info-file-info">
                    <span className="room-info-file-name">{label}</span>
                    <span className="room-info-file-meta">{meta}</span>
                  </span>
                </>
              )
              const key = `${a.kind}-${a.id}`

              if (a.kind === 'image') {
                return (
                  <button
                    key={key}
                    type="button"
                    className="room-info-file-row"
                    onClick={() => setLightboxSrc(getRoomImageUrl(room.id, a.id))}
                  >
                    {inner}
                  </button>
                )
              }
              if (getPreviewKind(a.filename ?? '')) {
                return (
                  <button
                    key={key}
                    type="button"
                    className="room-info-file-row"
                    onClick={() =>
                      setPreviewFile({
                        id: a.id,
                        filename: a.filename ?? label,
                        size_bytes: a.size_bytes,
                        content_type: a.content_type,
                      })
                    }
                  >
                    {inner}
                  </button>
                )
              }
              return (
                <a
                  key={key}
                  href={getRoomFileUrl(room.id, a.id)}
                  download={a.filename ?? undefined}
                  className="room-info-file-row"
                >
                  {inner}
                </a>
              )
            })}
          </div>
        )}
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
            <DisclosureChevron open={integrationsOpen} /> Integrations
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

      {canEditSettings && (
        <div className="room-info-section">
          <button
            type="button"
            className="room-info-settings-toggle"
            onClick={() => setSettingsOpen((v) => !v)}
          >
            <DisclosureChevron open={settingsOpen} /> Room settings
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
              <div className="toggle-row">
                <div className="toggle-label">
                  <span className="t">Private room</span>
                  <span className="d">Joinable by invite only</span>
                </div>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={isPrivateDraft}
                    onChange={(e) => setIsPrivateDraft(e.target.checked)}
                  />
                  <span className="track" />
                </label>
              </div>
              {roomError && <p className="room-info-error">{roomError}</p>}
              <button type="submit" className="btn-secondary">
                Save
              </button>
              {myRole === 'owner' && (
                <button type="button" className="room-info-danger-link" onClick={handleDelete}>
                  Delete room
                </button>
              )}
            </form>
          )}
        </div>
      )}

      {room.is_dm ? (
        <button type="button" className="room-info-leave" onClick={handleHideDm}>
          Hide conversation
        </button>
      ) : (
        <button
          type="button"
          className="room-info-leave"
          onClick={handleLeave}
          disabled={myRole === 'owner'}
          title={myRole === 'owner' ? 'Transfer ownership before leaving' : undefined}
        >
          Leave room
        </button>
      )}

      {lightboxSrc && <ImageLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />}
      {previewFile && (
        <FilePreviewModal
          roomId={room.id}
          file={previewFile}
          kind={getPreviewKind(previewFile.filename) ?? 'text'}
          onClose={() => setPreviewFile(null)}
        />
      )}
    </aside>
  )
}

import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  archiveRoom,
  deactivateUser,
  demoteUser,
  listAdminRooms,
  listAdminUsers,
  listAllEventSubscriptions,
  listAllIncomingWebhooks,
  listAuditLog,
  promoteUser,
  reactivateUser,
  resetUserPassword,
  transferOwnershipAdmin,
  unarchiveRoom,
} from '../api/admin'
import { ApiError } from '../api/client'
import { createApiToken, createBot, listApiTokens, listBots, revokeApiToken } from '../api/bots'
import { getUserAvatarUrl } from '../api/users'
import { useAuth } from '../context/AuthContext'
import { hashIndex } from '../lib/avatar'
import type {
  AdminRoom,
  AdminUser,
  ApiScope,
  ApiToken,
  AuditLogEntry,
  Bot,
  EventSubscriptionAdmin,
  WebhookIncomingAdmin,
} from '../types'
import { TopBar } from '../components/TopBar'
import { UserAvatar } from '../components/UserAvatar'
import './AdminPage.css'

type Tab = 'users' | 'rooms' | 'bots' | 'audit' | 'settings'

const AUDIT_PAGE_SIZE = 50
const ALL_SCOPES: ApiScope[] = ['read:messages', 'write:messages', 'manage:rooms']

export function AdminPage() {
  const { user: currentUser } = useAuth()
  const [tab, setTab] = useState<Tab>('users')
  const [users, setUsers] = useState<AdminUser[]>([])
  const [rooms, setRooms] = useState<AdminRoom[]>([])
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([])
  const [auditHasMore, setAuditHasMore] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [bots, setBots] = useState<Bot[]>([])
  const [newBotUsername, setNewBotUsername] = useState('')
  const [expandedBotId, setExpandedBotId] = useState<string | null>(null)
  const [tokensByBot, setTokensByBot] = useState<Record<string, ApiToken[]>>({})
  const [newTokenScopes, setNewTokenScopes] = useState<ApiScope[]>([])
  const [justCreatedToken, setJustCreatedToken] = useState<string | null>(null)
  const [incomingWebhooks, setIncomingWebhooks] = useState<WebhookIncomingAdmin[]>([])
  const [eventSubscriptions, setEventSubscriptions] = useState<EventSubscriptionAdmin[]>([])

  function reportError(err: unknown) {
    setError(err instanceof ApiError ? err.message : String(err))
  }

  function loadUsers() {
    listAdminUsers().then(setUsers).catch(reportError)
  }

  function loadRooms() {
    listAdminRooms().then(setRooms).catch(reportError)
  }

  function loadAuditLog() {
    listAuditLog(AUDIT_PAGE_SIZE, 0)
      .then((entries) => {
        setAuditLog(entries)
        setAuditHasMore(entries.length === AUDIT_PAGE_SIZE)
      })
      .catch(reportError)
  }

  function loadBots() {
    listBots().then(setBots).catch(reportError)
  }

  function loadWebhooksAdmin() {
    listAllIncomingWebhooks().then(setIncomingWebhooks).catch(reportError)
    listAllEventSubscriptions().then(setEventSubscriptions).catch(reportError)
  }

  useEffect(() => {
    if (tab === 'users') loadUsers()
    if (tab === 'rooms') {
      loadRooms()
      if (users.length === 0) loadUsers() // needed to resolve usernames for ownership transfer
    }
    if (tab === 'bots') {
      loadBots()
      loadWebhooksAdmin()
    }
    if (tab === 'audit') loadAuditLog()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  async function withBusy(id: string, action: () => Promise<void>) {
    setBusyId(id)
    setError(null)
    try {
      await action()
    } catch (err) {
      reportError(err)
    } finally {
      setBusyId(null)
    }
  }

  async function handleToggleActive(u: AdminUser) {
    await withBusy(u.id, async () => {
      const updated = u.is_active ? await deactivateUser(u.id) : await reactivateUser(u.id)
      setUsers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
    })
  }

  async function handleTogglePromote(u: AdminUser) {
    await withBusy(u.id, async () => {
      const updated = u.is_site_admin ? await demoteUser(u.id) : await promoteUser(u.id)
      setUsers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
    })
  }

  async function handleResetPassword(u: AdminUser) {
    const newPassword = prompt(`New password for ${u.username} (min 8 characters):`)
    if (!newPassword) return
    await withBusy(u.id, async () => {
      await resetUserPassword(u.id, newPassword)
    })
  }

  async function handleToggleArchive(r: AdminRoom) {
    await withBusy(r.id, async () => {
      const updated = r.is_archived ? await unarchiveRoom(r.id) : await archiveRoom(r.id)
      setRooms((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
    })
  }

  async function handleTransferOwnership(r: AdminRoom) {
    const username = prompt(`Transfer #${r.name} to which username? (must already be a member)`)
    if (!username) return
    const target = users.find((u) => u.username === username.trim())
    if (!target) {
      setError(`No known user named "${username}"`)
      return
    }
    await withBusy(r.id, async () => {
      const updated = await transferOwnershipAdmin(r.id, target.id)
      setRooms((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
    })
  }

  async function handleCreateBot() {
    const username = newBotUsername.trim()
    if (!username) return
    setError(null)
    try {
      await createBot(username)
      setNewBotUsername('')
      loadBots()
    } catch (err) {
      reportError(err)
    }
  }

  function toggleExpandBot(botId: string) {
    if (expandedBotId === botId) {
      setExpandedBotId(null)
      return
    }
    setExpandedBotId(botId)
    setNewTokenScopes([])
    setJustCreatedToken(null)
    if (!tokensByBot[botId]) {
      listApiTokens(botId)
        .then((tokens) => setTokensByBot((prev) => ({ ...prev, [botId]: tokens })))
        .catch(reportError)
    }
  }

  function toggleScope(scope: ApiScope) {
    setNewTokenScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    )
  }

  async function handleIssueToken(botId: string) {
    if (newTokenScopes.length === 0) return
    await withBusy(botId, async () => {
      const created = await createApiToken(botId, newTokenScopes)
      setJustCreatedToken(created.token)
      setNewTokenScopes([])
      const tokens = await listApiTokens(botId)
      setTokensByBot((prev) => ({ ...prev, [botId]: tokens }))
    })
  }

  async function handleRevokeToken(botId: string, tokenId: string) {
    await withBusy(tokenId, async () => {
      await revokeApiToken(tokenId)
      const tokens = await listApiTokens(botId)
      setTokensByBot((prev) => ({ ...prev, [botId]: tokens }))
    })
  }

  return (
    <div className="admin-page">
      <TopBar />
      <div className="admin-body">
        <div className="admin-header">
          <h1>Admin</h1>
          <Link to="/rooms" className="btn-secondary">
            Back to chat
          </Link>
        </div>

        <div className="admin-tabs" role="tablist">
          {(['users', 'rooms', 'bots', 'audit', 'settings'] as const).map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tab === t}
              className={`admin-tab${tab === t ? ' active' : ''}`}
              onClick={() => setTab(t)}
            >
              {t === 'users' && 'Users'}
              {t === 'rooms' && 'Rooms'}
              {t === 'bots' && 'Bots'}
              {t === 'audit' && 'Audit log'}
              {t === 'settings' && 'Settings'}
            </button>
          ))}
        </div>

        {error && <p className="admin-error">{error}</p>}

        {tab === 'users' && (
          <table className="admin-table">
            <thead>
              <tr>
                <th></th>
                <th>Username</th>
                <th>Email</th>
                <th>Status</th>
                <th>Role</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>
                    <UserAvatar
                      username={u.username}
                      colorIndex={hashIndex(u.username)}
                      size={28}
                      avatarUrl={u.avatar_filename ? getUserAvatarUrl(u.id, u.avatar_filename) : null}
                    />
                  </td>
                  <td>{u.display_name || u.username}</td>
                  <td>{u.email}</td>
                  <td>
                    <span className={`status-badge ${u.is_active ? 'active' : 'inactive'}`}>
                      {u.is_active ? 'Active' : 'Deactivated'}
                    </span>
                  </td>
                  <td>
                    <span className={`role-badge role-badge-${u.is_site_admin ? 'owner' : 'member'}`}>
                      {u.is_site_admin ? 'Site admin' : 'Member'}
                    </span>
                  </td>
                  <td className="admin-actions">
                    <button
                      type="button"
                      disabled={busyId === u.id || u.id === currentUser?.id}
                      onClick={() => handleToggleActive(u)}
                    >
                      {u.is_active ? 'Deactivate' : 'Reactivate'}
                    </button>
                    <button
                      type="button"
                      disabled={busyId === u.id || u.id === currentUser?.id}
                      onClick={() => handleTogglePromote(u)}
                    >
                      {u.is_site_admin ? 'Demote' : 'Promote'}
                    </button>
                    <button type="button" disabled={busyId === u.id} onClick={() => handleResetPassword(u)}>
                      Reset password
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {tab === 'rooms' && (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Visibility</th>
                <th>Status</th>
                <th>Members</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rooms.map((r) => (
                <tr key={r.id}>
                  <td>#{r.name}</td>
                  <td>{r.is_private ? 'Private' : 'Open'}</td>
                  <td>
                    <span className={`status-badge ${r.is_archived ? 'inactive' : 'active'}`}>
                      {r.is_archived ? 'Archived' : 'Active'}
                    </span>
                  </td>
                  <td>{r.member_count}</td>
                  <td className="admin-actions">
                    <button type="button" disabled={busyId === r.id} onClick={() => handleToggleArchive(r)}>
                      {r.is_archived ? 'Unarchive' : 'Archive'}
                    </button>
                    <button type="button" disabled={busyId === r.id} onClick={() => handleTransferOwnership(r)}>
                      Transfer ownership
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {tab === 'bots' && (
          <>
            <div className="admin-create-form">
              <input
                type="text"
                placeholder="Bot username"
                value={newBotUsername}
                onChange={(e) => setNewBotUsername(e.target.value)}
              />
              <button type="button" className="btn-secondary" onClick={handleCreateBot}>
                Create bot
              </button>
            </div>

            <table className="admin-table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {bots.map((b) => (
                  <Fragment key={b.id}>
                    <tr>
                      <td>{b.username}</td>
                      <td>
                        <span className={`status-badge ${b.is_active ? 'active' : 'inactive'}`}>
                          {b.is_active ? 'Active' : 'Deactivated'}
                        </span>
                      </td>
                      <td>{new Date(b.created_at).toLocaleDateString()}</td>
                      <td className="admin-actions">
                        <button type="button" onClick={() => toggleExpandBot(b.id)}>
                          {expandedBotId === b.id ? 'Hide tokens' : 'Manage tokens'}
                        </button>
                      </td>
                    </tr>
                    {expandedBotId === b.id && (
                      <tr>
                        <td colSpan={4} className="admin-bot-detail">
                          <div className="admin-token-list">
                            {(tokensByBot[b.id] ?? []).map((t) => (
                              <div key={t.id} className="admin-token-row">
                                <span className="admin-token-scopes">{t.scopes.join(', ')}</span>
                                <span className="admin-token-meta">
                                  {t.last_used_at
                                    ? `last used ${new Date(t.last_used_at).toLocaleDateString()}`
                                    : 'never used'}
                                </span>
                                <button
                                  type="button"
                                  className="admin-token-revoke"
                                  disabled={busyId === t.id}
                                  onClick={() => handleRevokeToken(b.id, t.id)}
                                >
                                  Revoke
                                </button>
                              </div>
                            ))}
                            {(tokensByBot[b.id] ?? []).length === 0 && (
                              <p className="admin-placeholder">No tokens yet.</p>
                            )}
                          </div>

                          <div className="admin-issue-token">
                            {ALL_SCOPES.map((scope) => (
                              <label key={scope} className="admin-scope-checkbox">
                                <input
                                  type="checkbox"
                                  checked={newTokenScopes.includes(scope)}
                                  onChange={() => toggleScope(scope)}
                                />
                                {scope}
                              </label>
                            ))}
                            <button
                              type="button"
                              className="btn-secondary"
                              disabled={newTokenScopes.length === 0 || busyId === b.id}
                              onClick={() => handleIssueToken(b.id)}
                            >
                              Issue token
                            </button>
                          </div>

                          {justCreatedToken && (
                            <p className="admin-new-token">
                              New token (copy it now, it won't be shown again):{' '}
                              <code>{justCreatedToken}</code>
                            </p>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>

            <h2 className="admin-subheading">Registered webhooks</h2>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Room</th>
                  <th>Type</th>
                  <th>Details</th>
                  <th>Created by</th>
                </tr>
              </thead>
              <tbody>
                {incomingWebhooks.map((w) => (
                  <tr key={w.id}>
                    <td>#{w.room_name}</td>
                    <td>Incoming</td>
                    <td>{w.description || '—'}</td>
                    <td>{w.created_by_username}</td>
                  </tr>
                ))}
                {eventSubscriptions.map((s) => (
                  <tr key={s.id}>
                    <td>{s.room_name ? `#${s.room_name}` : 'Global'}</td>
                    <td>Outgoing ({s.event_types.join(', ')})</td>
                    <td>{s.target_url}</td>
                    <td>{s.created_by_username}</td>
                  </tr>
                ))}
                {incomingWebhooks.length === 0 && eventSubscriptions.length === 0 && (
                  <tr>
                    <td colSpan={4} className="admin-placeholder">
                      No webhooks registered yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </>
        )}

        {tab === 'audit' && (
          <>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Target</th>
                </tr>
              </thead>
              <tbody>
                {auditLog.map((e) => (
                  <tr key={e.id}>
                    <td>{new Date(e.created_at).toLocaleString()}</td>
                    <td>{e.actor_username}</td>
                    <td>{e.action}</td>
                    <td>
                      {e.target_type} {e.target_id.slice(0, 8)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {auditHasMore && (
              <button
                type="button"
                className="btn-secondary admin-load-more"
                onClick={() =>
                  listAuditLog(AUDIT_PAGE_SIZE, auditLog.length)
                    .then((more) => {
                      setAuditLog((prev) => [...prev, ...more])
                      setAuditHasMore(more.length === AUDIT_PAGE_SIZE)
                    })
                    .catch(reportError)
                }
              >
                Load more
              </button>
            )}
          </>
        )}

        {tab === 'settings' && (
          <p className="admin-placeholder">
            System settings are coming in a future phase — there's nothing configurable yet.
          </p>
        )}
      </div>
    </div>
  )
}

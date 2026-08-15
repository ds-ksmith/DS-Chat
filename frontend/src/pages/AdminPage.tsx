import { Fragment, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  archiveRoom,
  deactivateUser,
  demoteUser,
  getSmtpSettings,
  inviteUser,
  listAdminRooms,
  listAdminUsers,
  listAllEventSubscriptions,
  listAllIncomingWebhooks,
  listAuditLog,
  listSiteInvites,
  promoteUser,
  reactivateUser,
  resetUserPassword,
  revokeSiteInvite,
  sendTestSmtpEmail,
  transferOwnershipAdmin,
  unarchiveRoom,
  updateSmtpSettings,
} from '../api/admin'
import { ApiError } from '../api/client'
import { createApiToken, createBot, listApiTokens, listBots, revokeApiToken } from '../api/bots'
import { getUserAvatarUrl } from '../api/users'
import { UserPicker } from '../components/UserPicker'
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
  SiteInvite,
  SmtpSettings,
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
  const [transferringRoomId, setTransferringRoomId] = useState<string | null>(null)
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

  const [siteInvites, setSiteInvites] = useState<SiteInvite[]>([])
  const [inviteEmail, setInviteEmail] = useState('')
  const [invitingBusy, setInvitingBusy] = useState(false)

  const [smtpSettings, setSmtpSettings] = useState<SmtpSettings | null>(null)
  const [smtpLoaded, setSmtpLoaded] = useState(false)
  const [smtpHost, setSmtpHost] = useState('')
  const [smtpPort, setSmtpPort] = useState('587')
  const [smtpUsername, setSmtpUsername] = useState('')
  const [smtpPassword, setSmtpPassword] = useState('')
  const [smtpFromAddress, setSmtpFromAddress] = useState('')
  const [smtpUseTls, setSmtpUseTls] = useState(true)
  const [smtpSaving, setSmtpSaving] = useState(false)
  const [smtpTestBusy, setSmtpTestBusy] = useState(false)
  const [smtpTestResult, setSmtpTestResult] = useState<string | null>(null)

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

  function loadSiteInvites() {
    listSiteInvites().then(setSiteInvites).catch(reportError)
  }

  function loadSmtpSettings() {
    getSmtpSettings()
      .then((cfg) => {
        setSmtpSettings(cfg)
        setSmtpLoaded(true)
        if (cfg) {
          setSmtpHost(cfg.host)
          setSmtpPort(String(cfg.port))
          setSmtpUsername(cfg.username ?? '')
          setSmtpFromAddress(cfg.from_address)
          setSmtpUseTls(cfg.use_tls)
        }
      })
      .catch(reportError)
  }

  useEffect(() => {
    if (tab === 'users') {
      loadUsers()
      loadSiteInvites()
    }
    if (tab === 'rooms') {
      loadRooms()
      if (users.length === 0) loadUsers() // needed to resolve usernames for ownership transfer
    }
    if (tab === 'bots') {
      loadBots()
      loadWebhooksAdmin()
    }
    if (tab === 'audit') loadAuditLog()
    if (tab === 'settings') loadSmtpSettings()
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

  function toggleTransfer(roomId: string) {
    setTransferringRoomId((prev) => (prev === roomId ? null : roomId))
  }

  async function handleTransferOwnership(r: AdminRoom, targetId: string) {
    await withBusy(r.id, async () => {
      const updated = await transferOwnershipAdmin(r.id, targetId)
      setRooms((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
    })
    setTransferringRoomId(null)
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

  async function handleInviteUser() {
    const email = inviteEmail.trim()
    if (!email) return
    setInvitingBusy(true)
    setError(null)
    try {
      await inviteUser(email)
      setInviteEmail('')
      loadSiteInvites()
    } catch (err) {
      reportError(err)
    } finally {
      setInvitingBusy(false)
    }
  }

  async function handleRevokeSiteInvite(invite: SiteInvite) {
    await withBusy(invite.id, async () => {
      const updated = await revokeSiteInvite(invite.id)
      setSiteInvites((prev) => prev.map((i) => (i.id === updated.id ? updated : i)))
    })
  }

  async function handleSaveSmtpSettings(e: FormEvent) {
    e.preventDefault()
    setSmtpSaving(true)
    setError(null)
    try {
      const updated = await updateSmtpSettings({
        host: smtpHost.trim(),
        port: Number(smtpPort),
        username: smtpUsername.trim() || null,
        password: smtpPassword || undefined,
        from_address: smtpFromAddress.trim(),
        use_tls: smtpUseTls,
      })
      setSmtpSettings(updated)
      setSmtpPassword('')
    } catch (err) {
      reportError(err)
    } finally {
      setSmtpSaving(false)
    }
  }

  async function handleSendTestEmail() {
    setSmtpTestBusy(true)
    setSmtpTestResult(null)
    try {
      await sendTestSmtpEmail()
      setSmtpTestResult('Test email sent — check your inbox.')
    } catch (err) {
      setSmtpTestResult(err instanceof ApiError ? err.message : String(err))
    } finally {
      setSmtpTestBusy(false)
    }
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
          <>
          <div className="admin-create-form">
            <input
              type="email"
              placeholder="Email address to invite"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
            />
            <button
              type="button"
              className="btn-secondary"
              disabled={invitingBusy || !inviteEmail.trim()}
              onClick={handleInviteUser}
            >
              {invitingBusy ? 'Sending…' : 'Send invite'}
            </button>
          </div>

          {siteInvites.length > 0 && (
            <div className="admin-invite-list">
              <div className="admin-invite-list-label">Pending invites</div>
              {siteInvites.map((invite) => (
                <div key={invite.id} className="admin-token-row">
                  <span className="admin-token-scopes">{invite.email}</span>
                  <span className={`invite-status-badge invite-status-${invite.status}`}>{invite.status}</span>
                  <span className="admin-token-meta">
                    {invite.status === 'pending' &&
                      `Expires ${new Date(invite.expires_at).toLocaleDateString()}`}
                  </span>
                  {invite.status === 'pending' && (
                    <button
                      type="button"
                      className="admin-token-revoke"
                      disabled={busyId === invite.id}
                      onClick={() => handleRevokeSiteInvite(invite)}
                    >
                      Revoke
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

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
                  <td>
                    <div className="admin-actions">
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
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </>
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
                <Fragment key={r.id}>
                  <tr>
                    <td>#{r.name}</td>
                    <td>{r.is_private ? 'Private' : 'Open'}</td>
                    <td>
                      <span className={`status-badge ${r.is_archived ? 'inactive' : 'active'}`}>
                        {r.is_archived ? 'Archived' : 'Active'}
                      </span>
                    </td>
                    <td>{r.member_count}</td>
                    <td>
                      <div className="admin-actions">
                        <button type="button" disabled={busyId === r.id} onClick={() => handleToggleArchive(r)}>
                          {r.is_archived ? 'Unarchive' : 'Archive'}
                        </button>
                        <button type="button" disabled={busyId === r.id} onClick={() => toggleTransfer(r.id)}>
                          {transferringRoomId === r.id ? 'Cancel' : 'Transfer ownership'}
                        </button>
                      </div>
                    </td>
                  </tr>
                  {transferringRoomId === r.id && (
                    <tr>
                      <td colSpan={5} className="admin-bot-detail">
                        <UserPicker
                          users={users}
                          excludeUserIds={[r.owner_id]}
                          placeholder="Search users to transfer ownership to…"
                          onSelect={(target) => handleTransferOwnership(r, target.id)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
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
                      <td>
                        <div className="admin-actions">
                          <button type="button" onClick={() => toggleExpandBot(b.id)}>
                            {expandedBotId === b.id ? 'Hide tokens' : 'Manage tokens'}
                          </button>
                        </div>
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
          <>
            <h2 className="admin-subheading">SMTP (outgoing email)</h2>
            {!smtpLoaded && <p className="admin-placeholder">Loading…</p>}
            {smtpLoaded && (
              <form className="admin-settings-form" onSubmit={handleSaveSmtpSettings}>
                <div className="admin-settings-row">
                  <label className="admin-settings-field">
                    Host
                    <input
                      type="text"
                      value={smtpHost}
                      onChange={(e) => setSmtpHost(e.target.value)}
                      placeholder="smtp.example.com"
                      required
                    />
                  </label>
                  <label className="admin-settings-field admin-settings-field-narrow">
                    Port
                    <input
                      type="number"
                      value={smtpPort}
                      onChange={(e) => setSmtpPort(e.target.value)}
                      min={1}
                      max={65535}
                      required
                    />
                  </label>
                </div>
                <div className="admin-settings-row">
                  <label className="admin-settings-field">
                    Username
                    <input
                      type="text"
                      value={smtpUsername}
                      onChange={(e) => setSmtpUsername(e.target.value)}
                    />
                  </label>
                  <label className="admin-settings-field">
                    Password
                    <input
                      type="password"
                      value={smtpPassword}
                      onChange={(e) => setSmtpPassword(e.target.value)}
                      placeholder={smtpSettings?.has_password ? 'Leave blank to keep current' : ''}
                    />
                  </label>
                </div>
                <label className="admin-settings-field">
                  From address
                  <input
                    type="email"
                    value={smtpFromAddress}
                    onChange={(e) => setSmtpFromAddress(e.target.value)}
                    placeholder="noreply@example.com"
                    required
                  />
                </label>
                <label className="admin-settings-checkbox">
                  <input
                    type="checkbox"
                    checked={smtpUseTls}
                    onChange={(e) => setSmtpUseTls(e.target.checked)}
                  />
                  Use TLS
                </label>
                <div className="admin-settings-actions">
                  <button type="submit" className="btn-primary" disabled={smtpSaving}>
                    {smtpSaving ? 'Saving…' : 'Save'}
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={smtpTestBusy || !smtpSettings}
                    onClick={handleSendTestEmail}
                  >
                    {smtpTestBusy ? 'Sending…' : 'Send test email'}
                  </button>
                </div>
                {smtpTestResult && <p className="admin-settings-test-result">{smtpTestResult}</p>}
              </form>
            )}
          </>
        )}
      </div>
    </div>
  )
}

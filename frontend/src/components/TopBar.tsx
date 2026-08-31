import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import logo from '../assets/logo.png'
import { updateAppearOffline } from '../api/auth'
import { ApiError } from '../api/client'
import { getUserAvatarUrl } from '../api/users'
import { useAuth } from '../context/AuthContext'
import { hashIndex } from '../lib/avatar'
import {
  getDesktopNotificationsEnabled,
  isDesktopNotificationsSupported,
  setDesktopNotificationsEnabled,
} from '../lib/desktopBridge'
import { getPushSubscriptionStatus, isPushSupported, subscribeToPush, unsubscribeFromPush } from '../lib/push'
import { AboutModal } from './AboutModal'
import { CustomEmojiManageModal } from './CustomEmojiManageModal'
import { ProfileModal } from './ProfileModal'
import { UserAvatar } from './UserAvatar'
import './TopBar.css'

// #49: inside DS Chat Desktop, notifications are delivered over the socket
// bridge instead of Web Push (Electron has no push delivery service
// configured) -- checked once, not re-derived per render, since bridge
// presence can't change over a session's lifetime.
const desktopMode = isDesktopNotificationsSupported()

export function TopBar() {
  const { user, updateUser, logout } = useAuth()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [customEmojiModalOpen, setCustomEmojiModalOpen] = useState(false)
  const [aboutModalOpen, setAboutModalOpen] = useState(false)
  const [pushSubscribed, setPushSubscribed] = useState(false)
  const [pushBusy, setPushBusy] = useState(false)
  const [pushError, setPushError] = useState<string | null>(null)
  const [desktopNotificationsEnabled, setDesktopNotificationsEnabledState] = useState(
    getDesktopNotificationsEnabled,
  )
  const [presenceBusy, setPresenceBusy] = useState(false)
  const [presenceError, setPresenceError] = useState<string | null>(null)

  useEffect(() => {
    // Never touch PushManager at all in desktop mode -- Electron has no
    // push service configured, so even the read-only getSubscription()
    // check has no reason to run there.
    if (desktopMode) return
    getPushSubscriptionStatus().then(setPushSubscribed)
  }, [])

  function handleToggleDesktopNotifications() {
    const next = !desktopNotificationsEnabled
    setDesktopNotificationsEnabled(next)
    setDesktopNotificationsEnabledState(next)
  }

  async function handleTogglePush() {
    setPushBusy(true)
    setPushError(null)
    try {
      if (pushSubscribed) {
        await unsubscribeFromPush()
        setPushSubscribed(false)
      } else {
        await subscribeToPush()
        setPushSubscribed(true)
      }
    } catch (err) {
      setPushError(err instanceof Error ? err.message : String(err))
    } finally {
      setPushBusy(false)
    }
  }

  async function handleTogglePresence() {
    if (!user) return
    setPresenceBusy(true)
    setPresenceError(null)
    try {
      const updated = await updateAppearOffline(!user.appear_offline)
      updateUser(updated)
    } catch (err) {
      setPresenceError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setPresenceBusy(false)
    }
  }

  if (!user) return null

  return (
    <header className="top-bar">
      <div className="top-bar-brand">
        <img src={logo} alt="" className="top-bar-logo" />
        <span className="top-bar-title">DS Chat</span>
      </div>

      <div className="top-bar-user">
        <button
          type="button"
          className="top-bar-avatar"
          onClick={() => setMenuOpen((v) => !v)}
          aria-expanded={menuOpen}
          aria-label="Account menu"
        >
          <UserAvatar
            username={user.username}
            colorIndex={hashIndex(user.username)}
            size={30}
            avatarUrl={user.avatar_filename ? getUserAvatarUrl(user.id, user.avatar_filename) : null}
            status={user.appear_offline ? 'offline' : 'online'}
          />
        </button>
        {menuOpen && (
          <>
            <div className="top-bar-menu-scrim" onClick={() => setMenuOpen(false)} />
            <div className="top-bar-menu" role="menu">
              <div className="top-bar-menu-username">{user.display_name || user.username}</div>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false)
                  setProfileModalOpen(true)
                }}
              >
                Profile settings
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false)
                  setCustomEmojiModalOpen(true)
                }}
              >
                Custom emoji
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false)
                  navigate('/help')
                }}
              >
                Help
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false)
                  setAboutModalOpen(true)
                }}
              >
                About
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={handleTogglePresence}
                disabled={presenceBusy}
              >
                {user.appear_offline ? 'Show as online' : 'Appear offline'}
              </button>
              {presenceError && <div className="top-bar-menu-error">{presenceError}</div>}
              {user.is_site_admin && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false)
                    navigate('/admin')
                  }}
                >
                  Admin
                </button>
              )}
              {desktopMode ? (
                <button type="button" role="menuitem" onClick={handleToggleDesktopNotifications}>
                  {desktopNotificationsEnabled ? 'Disable notifications' : 'Enable notifications'}
                </button>
              ) : (
                isPushSupported() && (
                  <button
                    type="button"
                    role="menuitem"
                    onClick={handleTogglePush}
                    disabled={pushBusy}
                  >
                    {pushSubscribed ? 'Disable notifications' : 'Enable notifications'}
                  </button>
                )
              )}
              {pushError && <div className="top-bar-menu-error">{pushError}</div>}
              <button type="button" role="menuitem" onClick={() => logout()}>
                Log out
              </button>
            </div>
          </>
        )}
      </div>
      {profileModalOpen && <ProfileModal onClose={() => setProfileModalOpen(false)} />}
      {customEmojiModalOpen && <CustomEmojiManageModal onClose={() => setCustomEmojiModalOpen(false)} />}
      {aboutModalOpen && <AboutModal onClose={() => setAboutModalOpen(false)} />}
    </header>
  )
}

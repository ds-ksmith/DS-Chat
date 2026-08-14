import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import logo from '../assets/logo.png'
import { getUserAvatarUrl } from '../api/users'
import { useAuth } from '../context/AuthContext'
import { hashIndex } from '../lib/avatar'
import { getPushSubscriptionStatus, isPushSupported, subscribeToPush, unsubscribeFromPush } from '../lib/push'
import { ProfileModal } from './ProfileModal'
import { UserAvatar } from './UserAvatar'
import './TopBar.css'

export function TopBar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [pushSubscribed, setPushSubscribed] = useState(false)
  const [pushBusy, setPushBusy] = useState(false)
  const [pushError, setPushError] = useState<string | null>(null)

  useEffect(() => {
    getPushSubscriptionStatus().then(setPushSubscribed)
  }, [])

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

  if (!user) return null

  return (
    <header className="top-bar">
      <div className="top-bar-brand">
        <img src={logo} alt="" className="top-bar-logo" />
        <span className="top-bar-title">KeepItTalking</span>
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
              {isPushSupported() && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={handleTogglePush}
                  disabled={pushBusy}
                >
                  {pushSubscribed ? 'Disable notifications' : 'Enable notifications'}
                </button>
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
    </header>
  )
}

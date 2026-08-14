import { useEffect, useState } from 'react'
import logo from '../assets/logo.png'
import { useAuth } from '../context/AuthContext'
import { initials } from '../lib/avatar'
import { getPushSubscriptionStatus, isPushSupported, subscribeToPush, unsubscribeFromPush } from '../lib/push'
import './TopBar.css'

export function TopBar() {
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
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
          {initials(user.username)}
        </button>
        {menuOpen && (
          <>
            <div className="top-bar-menu-scrim" onClick={() => setMenuOpen(false)} />
            <div className="top-bar-menu" role="menu">
              <div className="top-bar-menu-username">{user.username}</div>
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
    </header>
  )
}

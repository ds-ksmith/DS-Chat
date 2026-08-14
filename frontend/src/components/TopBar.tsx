import { useState } from 'react'
import logo from '../assets/logo.png'
import { useAuth } from '../context/AuthContext'
import { initials } from '../lib/avatar'
import './TopBar.css'

export function TopBar() {
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)

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

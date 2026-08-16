import { useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { changePassword, removeAvatar, updateProfile, updateTheme, uploadAvatar } from '../api/auth'
import { ApiError } from '../api/client'
import { getUserAvatarUrl } from '../api/users'
import { useAuth } from '../context/AuthContext'
import { hashIndex } from '../lib/avatar'
import type { ThemeName } from '../types'
import { UserAvatar } from './UserAvatar'
import './Modal.css'

const THEME_OPTIONS: { name: ThemeName; label: string }[] = [
  { name: 'dark', label: 'Dark' },
  { name: 'light', label: 'Light' },
  { name: 'midnight', label: 'Midnight' },
  { name: 'sunset', label: 'Sunset' },
]

interface ProfileModalProps {
  onClose: () => void
}

export function ProfileModal({ onClose }: ProfileModalProps) {
  const { user, updateUser } = useAuth()
  const [displayName, setDisplayName] = useState(user?.display_name ?? '')
  const [error, setError] = useState<string | null>(null)
  const [savingName, setSavingName] = useState(false)
  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [themeError, setThemeError] = useState<string | null>(null)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordSuccess, setPasswordSuccess] = useState(false)
  const [savingPassword, setSavingPassword] = useState(false)

  if (!user) return null

  async function handleSaveName(e: FormEvent) {
    e.preventDefault()
    setSavingName(true)
    setError(null)
    try {
      const updated = await updateProfile(displayName.trim() || null)
      updateUser(updated)
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setSavingName(false)
    }
  }

  async function handleFileSelected(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploadingAvatar(true)
    setError(null)
    try {
      const updated = await uploadAvatar(file)
      updateUser(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setUploadingAvatar(false)
    }
  }

  async function handleRemoveAvatar() {
    setError(null)
    try {
      const updated = await removeAvatar()
      updateUser(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    }
  }

  async function handleSelectTheme(theme: ThemeName) {
    // Instant visual feedback, then persist -- mirrors avatar upload's
    // apply-immediately pattern rather than requiring a separate Save.
    document.documentElement.setAttribute('data-theme', theme)
    setThemeError(null)
    try {
      const updated = await updateTheme(theme)
      updateUser(updated)
    } catch (err) {
      // Revert the optimistic DOM change if it didn't actually persist.
      document.documentElement.setAttribute('data-theme', user?.theme ?? 'dark')
      setThemeError(err instanceof ApiError ? err.message : String(err))
    }
  }

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault()
    setPasswordError(null)
    setPasswordSuccess(false)
    if (newPassword !== confirmPassword) {
      setPasswordError("New passwords don't match")
      return
    }
    setSavingPassword(true)
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setPasswordSuccess(true)
    } catch (err) {
      setPasswordError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setSavingPassword(false)
    }
  }

  const avatarUrl = user.avatar_filename ? getUserAvatarUrl(user.id, user.avatar_filename) : null

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Profile settings</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="profile-modal-avatar-row">
          <UserAvatar
            username={user.username}
            colorIndex={hashIndex(user.username)}
            size={64}
            avatarUrl={avatarUrl}
            status={user.appear_offline ? 'offline' : 'online'}
          />
          <div className="profile-modal-avatar-actions">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/gif,image/webp"
              className="modal-hidden-file-input"
              onChange={handleFileSelected}
            />
            <button
              type="button"
              className="btn-secondary"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadingAvatar}
            >
              {uploadingAvatar ? 'Uploading…' : 'Upload photo'}
            </button>
            {avatarUrl && (
              <button type="button" className="btn-secondary" onClick={handleRemoveAvatar}>
                Remove photo
              </button>
            )}
          </div>
        </div>

        <hr className="modal-divider" />

        <div className="modal-field-label">Theme</div>
        <div className="theme-swatch-grid">
          {THEME_OPTIONS.map((option) => (
            <button
              key={option.name}
              type="button"
              className={`theme-swatch theme-swatch-${option.name}${
                (user.theme ?? 'dark') === option.name ? ' theme-swatch-selected' : ''
              }`}
              onClick={() => handleSelectTheme(option.name)}
              aria-pressed={(user.theme ?? 'dark') === option.name}
            >
              <span className="theme-swatch-preview" aria-hidden="true">
                <span className="theme-swatch-accent" />
              </span>
              <span className="theme-swatch-label">{option.label}</span>
            </button>
          ))}
        </div>
        {themeError && <p className="modal-error">{themeError}</p>}

        <hr className="modal-divider" />

        <form onSubmit={handleSaveName}>
          <div className="modal-field-label">Display name</div>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder={user.username}
            maxLength={50}
          />
          {error && <p className="modal-error">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Close
            </button>
            <button type="submit" className="btn-primary" disabled={savingName}>
              Save
            </button>
          </div>
        </form>

        <hr className="modal-divider" />

        <form onSubmit={handleChangePassword}>
          <div className="modal-field-label">Change password</div>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder="Current password"
            autoComplete="current-password"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="New password"
            autoComplete="new-password"
            minLength={8}
          />
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Confirm new password"
            autoComplete="new-password"
            minLength={8}
          />
          {passwordError && <p className="modal-error">{passwordError}</p>}
          {passwordSuccess && <p className="modal-success">Password updated.</p>}
          <div className="modal-actions">
            <button
              type="submit"
              className="btn-primary"
              disabled={savingPassword || !currentPassword || !newPassword || !confirmPassword}
            >
              {savingPassword ? 'Saving…' : 'Update password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

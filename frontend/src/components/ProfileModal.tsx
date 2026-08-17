import { useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { changePassword, removeAvatar, updateProfile, updateTheme, uploadAvatar } from '../api/auth'
import { ApiError } from '../api/client'
import { getUserAvatarUrl } from '../api/users'
import { useAuth } from '../context/AuthContext'
import { hashIndex } from '../lib/avatar'
import { applyTheme, DEFAULT_CUSTOM_COLORS } from '../lib/theme'
import type { CustomThemeColors, ThemeName } from '../types'
import { UserAvatar } from './UserAvatar'
import './Modal.css'

const THEME_OPTIONS: { name: ThemeName; label: string }[] = [
  { name: 'dark', label: 'Dark' },
  { name: 'light', label: 'Light' },
  { name: 'midnight', label: 'Midnight' },
  { name: 'sunset', label: 'Sunset' },
]

const CUSTOM_COLOR_FIELDS: { key: keyof Omit<CustomThemeColors, 'color_scheme'>; label: string }[] = [
  { key: 'void', label: 'Background' },
  { key: 'void_2', label: 'Sidebar background' },
  { key: 'surface', label: 'Surface' },
  { key: 'surface_2', label: 'Surface (secondary)' },
  { key: 'border', label: 'Border' },
  { key: 'text', label: 'Text' },
  { key: 'muted', label: 'Muted text' },
  { key: 'accent', label: 'Accent' },
  { key: 'accent_2', label: 'Accent (secondary)' },
  { key: 'accent_3', label: 'Accent (tertiary)' },
  { key: 'highlight', label: 'Highlight' },
  { key: 'danger', label: 'Danger' },
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
  const [customColors, setCustomColors] = useState<CustomThemeColors>(
    user?.custom_theme_colors ?? DEFAULT_CUSTOM_COLORS,
  )
  const [customColorsDirty, setCustomColorsDirty] = useState(false)
  const [savingColors, setSavingColors] = useState(false)

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
      handleClose()
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
    // For 'custom', this always sends the current draft palette alongside
    // the theme name (previously-saved colors if any, else the defaults),
    // so selecting Custom never leaves theme='custom' persisted with no
    // palette behind it.
    applyTheme(theme, theme === 'custom' ? customColors : null)
    setThemeError(null)
    try {
      const updated = await updateTheme(theme, theme === 'custom' ? customColors : undefined)
      updateUser(updated)
      setCustomColorsDirty(false)
    } catch (err) {
      // Revert the optimistic DOM change if it didn't actually persist.
      applyTheme(user?.theme ?? 'dark', user?.custom_theme_colors ?? null)
      setThemeError(err instanceof ApiError ? err.message : String(err))
    }
  }

  function handleCustomColorChange(key: keyof CustomThemeColors, value: string) {
    const next = { ...customColors, [key]: value }
    setCustomColors(next)
    setCustomColorsDirty(true)
    // Live preview only -- deliberately not persisted per keystroke (a
    // native color input fires continuously while dragging), see
    // handleSaveColors for the actual persist step.
    applyTheme('custom', next)
  }

  async function handleSaveColors() {
    setSavingColors(true)
    setThemeError(null)
    try {
      const updated = await updateTheme('custom', customColors)
      updateUser(updated)
      setCustomColorsDirty(false)
    } catch (err) {
      setThemeError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setSavingColors(false)
    }
  }

  function handleClose() {
    // Unsaved color edits were only ever a live preview -- revert to
    // whatever's actually persisted so closing without saving doesn't leave
    // the app visually stuck on a draft.
    if (customColorsDirty) applyTheme(user?.theme ?? 'dark', user?.custom_theme_colors ?? null)
    onClose()
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
    <div className="modal-scrim" onClick={handleClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Profile settings</h2>
          <button type="button" className="modal-close" onClick={handleClose} aria-label="Close">
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
          <button
            type="button"
            className={`theme-swatch${user.theme === 'custom' ? ' theme-swatch-selected' : ''}`}
            onClick={() => handleSelectTheme('custom')}
            aria-pressed={user.theme === 'custom'}
          >
            <span
              className="theme-swatch-preview"
              aria-hidden="true"
              style={{ background: customColors.void }}
            >
              <span className="theme-swatch-accent" style={{ background: customColors.accent }} />
            </span>
            <span className="theme-swatch-label">Custom</span>
          </button>
        </div>
        {themeError && <p className="modal-error">{themeError}</p>}

        {user.theme === 'custom' && (
          <div className="custom-theme-editor">
            <div className="custom-theme-grid">
              {CUSTOM_COLOR_FIELDS.map((field) => (
                <label key={field.key} className="custom-theme-field">
                  <input
                    type="color"
                    value={customColors[field.key]}
                    onChange={(e) => handleCustomColorChange(field.key, e.target.value)}
                  />
                  <span>{field.label}</span>
                </label>
              ))}
            </div>
            <div className="custom-theme-scheme">
              <span>Native controls (scrollbars, form inputs)</span>
              <div className="custom-theme-scheme-toggle">
                <button
                  type="button"
                  className={`btn-secondary${customColors.color_scheme === 'light' ? ' custom-theme-scheme-active' : ''}`}
                  onClick={() => handleCustomColorChange('color_scheme', 'light')}
                >
                  Light
                </button>
                <button
                  type="button"
                  className={`btn-secondary${customColors.color_scheme === 'dark' ? ' custom-theme-scheme-active' : ''}`}
                  onClick={() => handleCustomColorChange('color_scheme', 'dark')}
                >
                  Dark
                </button>
              </div>
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="btn-primary"
                onClick={handleSaveColors}
                disabled={savingColors || !customColorsDirty}
              >
                {savingColors ? 'Saving…' : 'Save colors'}
              </button>
            </div>
          </div>
        )}

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
            <button type="button" className="btn-secondary" onClick={handleClose}>
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

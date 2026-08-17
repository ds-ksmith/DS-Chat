import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { changePassword, me, removeAvatar, updateProfile, updateTheme, uploadAvatar } from '../api/auth'
import { ApiError } from '../api/client'
import {
  activateCustomTheme,
  createCustomTheme,
  deleteCustomTheme,
  listCustomThemes,
  updateCustomTheme,
} from '../api/customThemes'
import { getUserAvatarUrl } from '../api/users'
import { useAuth } from '../context/AuthContext'
import { hashIndex } from '../lib/avatar'
import { applyTheme, DEFAULT_CUSTOM_COLORS } from '../lib/theme'
import type { CustomTheme, CustomThemeColors } from '../types'
import { CustomThemePreview } from './CustomThemePreview'
import { UserAvatar } from './UserAvatar'
import './Modal.css'

const THEME_OPTIONS: { name: 'dark' | 'light' | 'midnight' | 'sunset'; label: string }[] = [
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

  const [customThemes, setCustomThemes] = useState<CustomTheme[]>([])
  const [editingThemeId, setEditingThemeId] = useState<string | null>(null)
  const [editNameDraft, setEditNameDraft] = useState('')
  const [editColorsDraft, setEditColorsDraft] = useState<CustomThemeColors>(DEFAULT_CUSTOM_COLORS)
  const [savingThemeEdit, setSavingThemeEdit] = useState(false)
  const [highlightedField, setHighlightedField] = useState<keyof CustomThemeColors | null>(null)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordSuccess, setPasswordSuccess] = useState(false)
  const [savingPassword, setSavingPassword] = useState(false)

  useEffect(() => {
    listCustomThemes()
      .then(setCustomThemes)
      .catch(() => {
        // Non-critical -- the saved-themes list just stays empty; presets
        // and everything else in this modal still work fine.
      })
  }, [])

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

  async function handleSelectPreset(theme: 'dark' | 'light' | 'midnight' | 'sunset') {
    // Instant visual feedback, then persist -- mirrors avatar upload's
    // apply-immediately pattern rather than requiring a separate Save.
    applyTheme(theme, null)
    setThemeError(null)
    try {
      const updated = await updateTheme(theme)
      updateUser(updated)
    } catch (err) {
      applyTheme(user?.theme ?? 'dark', user?.active_custom_theme?.colors ?? null)
      setThemeError(err instanceof ApiError ? err.message : String(err))
    }
  }

  async function handleActivateCustomTheme(theme: CustomTheme) {
    applyTheme('custom', theme.colors)
    setThemeError(null)
    try {
      const updated = await activateCustomTheme(theme.id)
      updateUser(updated)
    } catch (err) {
      applyTheme(user?.theme ?? 'dark', user?.active_custom_theme?.colors ?? null)
      setThemeError(err instanceof ApiError ? err.message : String(err))
    }
  }

  async function handleCreateCustomTheme() {
    setThemeError(null)
    try {
      const created = await createCustomTheme('New theme', DEFAULT_CUSTOM_COLORS)
      setCustomThemes((prev) => [...prev, created])
      await handleActivateCustomTheme(created)
      openEditor(created)
    } catch (err) {
      setThemeError(err instanceof ApiError ? err.message : String(err))
    }
  }

  function openEditor(theme: CustomTheme) {
    setEditingThemeId(theme.id)
    setEditNameDraft(theme.name)
    setEditColorsDraft(theme.colors)
    setThemeError(null)
    setHighlightedField(null)
  }

  function closeEditor() {
    // Only ever live-previewed on screen if this theme was already the
    // active one (see handleEditColorChange) -- revert that preview back
    // to whatever's actually persisted if it was never saved.
    if (editingThemeId && user?.active_custom_theme?.id === editingThemeId) {
      applyTheme(user.theme, user.active_custom_theme.colors)
    }
    setEditingThemeId(null)
    setHighlightedField(null)
  }

  function handleEditColorChange(key: keyof CustomThemeColors, value: string) {
    const next = { ...editColorsDraft, [key]: value }
    setEditColorsDraft(next)
    // Only reflect on the whole page live if the theme being edited is
    // already the active one -- editing a theme you're not currently using
    // shouldn't hijack what's on screen right now.
    if (editingThemeId && user?.active_custom_theme?.id === editingThemeId) {
      applyTheme('custom', next)
    }
  }

  async function handleSaveThemeEdit() {
    if (!editingThemeId || !user) return
    setSavingThemeEdit(true)
    setThemeError(null)
    try {
      const updated = await updateCustomTheme(editingThemeId, {
        name: editNameDraft.trim() || 'Untitled',
        colors: editColorsDraft,
      })
      setCustomThemes((prev) => prev.map((t) => (t.id === updated.id ? updated : t)))
      if (user.active_custom_theme?.id === updated.id) {
        updateUser({ ...user, active_custom_theme: updated })
      }
      setEditingThemeId(null)
    } catch (err) {
      setThemeError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setSavingThemeEdit(false)
    }
  }

  async function handleDeleteCustomTheme(theme: CustomTheme) {
    if (!confirm(`Delete "${theme.name}"? This can't be undone.`) || !user) return
    setThemeError(null)
    try {
      await deleteCustomTheme(theme.id)
      setCustomThemes((prev) => prev.filter((t) => t.id !== theme.id))
      if (editingThemeId === theme.id) setEditingThemeId(null)
      if (user.active_custom_theme?.id === theme.id) {
        // The backend fell back to a preset for us -- pick that up rather
        // than guessing what it chose.
        const refreshed = await me()
        updateUser(refreshed)
        applyTheme(refreshed.theme, refreshed.active_custom_theme?.colors ?? null)
      }
    } catch (err) {
      setThemeError(err instanceof ApiError ? err.message : String(err))
    }
  }

  function handleClose() {
    if (editingThemeId) closeEditor()
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
  const editingTheme = customThemes.find((t) => t.id === editingThemeId) ?? null

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
              onClick={() => handleSelectPreset(option.name)}
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

        <div className="modal-field-label">My custom themes</div>
        <div className="theme-swatch-grid">
          {customThemes.map((theme) => {
            const active = user.theme === 'custom' && user.active_custom_theme?.id === theme.id
            return (
              <div key={theme.id} className={`custom-theme-swatch${active ? ' theme-swatch-selected' : ''}`}>
                <button
                  type="button"
                  className="theme-swatch custom-theme-swatch-select"
                  onClick={() => handleActivateCustomTheme(theme)}
                  aria-pressed={active}
                >
                  <span
                    className="theme-swatch-preview"
                    aria-hidden="true"
                    style={{ background: theme.colors.void }}
                  >
                    <span className="theme-swatch-accent" style={{ background: theme.colors.accent }} />
                  </span>
                  <span className="theme-swatch-label">{theme.name}</span>
                </button>
                <div className="custom-theme-swatch-actions">
                  <button
                    type="button"
                    className="custom-theme-swatch-icon-btn"
                    onClick={() => (editingThemeId === theme.id ? closeEditor() : openEditor(theme))}
                    aria-label={`Edit ${theme.name}`}
                    title="Edit"
                  >
                    <svg width="13" height="13" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                      <path
                        d="M13.5 3.5 16.5 6.5 7 16 3 17 4 13 13.5 3.5Z"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                  <button
                    type="button"
                    className="custom-theme-swatch-icon-btn"
                    onClick={() => handleDeleteCustomTheme(theme)}
                    aria-label={`Delete ${theme.name}`}
                    title="Delete"
                  >
                    <svg width="13" height="13" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                      <path
                        d="M4 6h12M8 6V4h4v2m-6 0 .7 10.5A1 1 0 0 0 7.7 17h4.6a1 1 0 0 0 1-.95L14 6"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            )
          })}
          <button type="button" className="theme-swatch custom-theme-new" onClick={handleCreateCustomTheme}>
            <span className="theme-swatch-preview theme-swatch-preview-new" aria-hidden="true">
              +
            </span>
            <span className="theme-swatch-label">New</span>
          </button>
        </div>

        {editingTheme && (
          <div className="custom-theme-editor">
            <input
              type="text"
              className="custom-theme-name-input"
              value={editNameDraft}
              onChange={(e) => setEditNameDraft(e.target.value)}
              placeholder="Theme name"
              maxLength={50}
            />
            <CustomThemePreview
              colors={editColorsDraft}
              highlightedField={highlightedField}
              onHighlight={setHighlightedField}
            />
            <div className="custom-theme-grid">
              {CUSTOM_COLOR_FIELDS.map((field) => (
                <label
                  key={field.key}
                  className={`custom-theme-field${highlightedField === field.key ? ' custom-theme-field-highlighted' : ''}`}
                  onMouseEnter={() => setHighlightedField(field.key)}
                  onMouseLeave={() => setHighlightedField(null)}
                >
                  <input
                    type="color"
                    value={editColorsDraft[field.key]}
                    onChange={(e) => handleEditColorChange(field.key, e.target.value)}
                    onFocus={() => setHighlightedField(field.key)}
                    onBlur={() => setHighlightedField(null)}
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
                  className={`btn-secondary${editColorsDraft.color_scheme === 'light' ? ' custom-theme-scheme-active' : ''}`}
                  onClick={() => handleEditColorChange('color_scheme', 'light')}
                >
                  Light
                </button>
                <button
                  type="button"
                  className={`btn-secondary${editColorsDraft.color_scheme === 'dark' ? ' custom-theme-scheme-active' : ''}`}
                  onClick={() => handleEditColorChange('color_scheme', 'dark')}
                >
                  Dark
                </button>
              </div>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn-secondary" onClick={closeEditor}>
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={handleSaveThemeEdit}
                disabled={savingThemeEdit}
              >
                {savingThemeEdit ? 'Saving…' : 'Save'}
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

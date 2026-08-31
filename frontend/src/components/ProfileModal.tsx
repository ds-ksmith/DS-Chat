import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import {
  changePassword,
  listSessions,
  me,
  removeAvatar,
  revokeSession,
  updateEmojiScale,
  updateProfile,
  updateTextScale,
  updateTheme,
  uploadAvatar,
} from '../api/auth'
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
import { applyTextScale, applyTheme, DEFAULT_CUSTOM_COLORS } from '../lib/theme'
import type { CustomTheme, CustomThemeColors, EmojiScale, TextScale, UserSession } from '../types'
import { ThemeBuilderModal } from './ThemeBuilderModal'
import { UserAvatar } from './UserAvatar'
import './Modal.css'

const THEME_OPTIONS: { name: 'dark' | 'light' | 'midnight' | 'sunset'; label: string }[] = [
  { name: 'dark', label: 'Dark' },
  { name: 'light', label: 'Light' },
  { name: 'midnight', label: 'Midnight' },
  { name: 'sunset', label: 'Sunset' },
]

// #71: the "Aa" preview scales with each option's own size, the standard
// way a text-size picker shows what it does without a separate demo area.
const TEXT_SCALE_OPTIONS: { name: TextScale; label: string; previewSize: string }[] = [
  { name: 'small', label: 'Small', previewSize: '0.8rem' },
  { name: 'normal', label: 'Normal', previewSize: '1rem' },
  { name: 'large', label: 'Large', previewSize: '1.25rem' },
  { name: 'xlarge', label: 'Extra large', previewSize: '1.5rem' },
]

// #71: independent of text size -- only scales emoji rendered in message
// text (see MessageContent.tsx's --emoji-scale). The preview uses an
// actual emoji so it demonstrates itself the same way the text-size
// options do with "Aa".
const EMOJI_SCALE_OPTIONS: { name: EmojiScale; label: string; previewSize: string }[] = [
  { name: 'small', label: 'Small', previewSize: '1rem' },
  { name: 'normal', label: 'Normal', previewSize: '1.25rem' },
  { name: 'large', label: 'Large', previewSize: '1.6rem' },
  { name: 'xlarge', label: 'Extra large', previewSize: '2rem' },
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
  const { user, updateUser, logout } = useAuth()
  const [displayName, setDisplayName] = useState(user?.display_name ?? '')
  const [error, setError] = useState<string | null>(null)
  const [savingName, setSavingName] = useState(false)
  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [themeError, setThemeError] = useState<string | null>(null)
  const [textScaleError, setTextScaleError] = useState<string | null>(null)
  const [emojiScaleError, setEmojiScaleError] = useState<string | null>(null)

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

  const [sessions, setSessions] = useState<UserSession[]>([])
  const [sessionsError, setSessionsError] = useState<string | null>(null)
  const [revokingSessionId, setRevokingSessionId] = useState<string | null>(null)

  useEffect(() => {
    listCustomThemes()
      .then(setCustomThemes)
      .catch(() => {
        // Non-critical -- the saved-themes list just stays empty; presets
        // and everything else in this modal still work fine.
      })
    listSessions()
      .then(setSessions)
      .catch(() => {
        // Same non-critical treatment -- an empty list just means this
        // section renders no rows rather than failing the whole modal.
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

  async function handleSelectTextScale(scale: TextScale) {
    // Same instant-apply-then-persist pattern as handleSelectPreset above.
    applyTextScale(scale)
    setTextScaleError(null)
    try {
      const updated = await updateTextScale(scale)
      updateUser(updated)
    } catch (err) {
      applyTextScale(user?.text_scale ?? null)
      setTextScaleError(err instanceof ApiError ? err.message : String(err))
    }
  }

  async function handleSelectEmojiScale(scale: EmojiScale) {
    // No instant-apply DOM mutation here (unlike theme/text scale) -- it's
    // just a value MessageContent reads from `user` on its next render, so
    // persisting and updating that is the whole job.
    setEmojiScaleError(null)
    try {
      const updated = await updateEmojiScale(scale)
      updateUser(updated)
    } catch (err) {
      setEmojiScaleError(err instanceof ApiError ? err.message : String(err))
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

  async function handleRevokeSession(session: UserSession) {
    setSessionsError(null)
    setRevokingSessionId(session.id)
    try {
      if (session.is_current) {
        // Revoking your own current session is really just "sign out" --
        // go through the normal logout path so local auth state (and the
        // rest of the app) clears immediately, instead of waiting for the
        // next request to organically 401.
        await logout()
        return
      }
      await revokeSession(session.id)
      setSessions((prev) => prev.filter((s) => s.id !== session.id))
    } catch (err) {
      setSessionsError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setRevokingSessionId(null)
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

        <div className="modal-field-label">Text size</div>
        <div className="text-scale-options">
          {TEXT_SCALE_OPTIONS.map((option) => (
            <button
              key={option.name}
              type="button"
              className={`text-scale-option${
                (user.text_scale ?? 'normal') === option.name ? ' text-scale-option-selected' : ''
              }`}
              onClick={() => handleSelectTextScale(option.name)}
              aria-pressed={(user.text_scale ?? 'normal') === option.name}
            >
              <span className="text-scale-option-preview" style={{ fontSize: option.previewSize }}>
                Aa
              </span>
              <span className="text-scale-option-label">{option.label}</span>
            </button>
          ))}
        </div>
        {textScaleError && <p className="modal-error">{textScaleError}</p>}

        <div className="modal-field-label">Emoji size</div>
        <div className="text-scale-options">
          {EMOJI_SCALE_OPTIONS.map((option) => (
            <button
              key={option.name}
              type="button"
              className={`text-scale-option${
                (user.emoji_scale ?? 'normal') === option.name ? ' text-scale-option-selected' : ''
              }`}
              onClick={() => handleSelectEmojiScale(option.name)}
              aria-pressed={(user.emoji_scale ?? 'normal') === option.name}
            >
              <span className="text-scale-option-preview" style={{ fontSize: option.previewSize }}>
                🎉
              </span>
              <span className="text-scale-option-label">{option.label}</span>
            </button>
          ))}
        </div>
        {emojiScaleError && <p className="modal-error">{emojiScaleError}</p>}

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
          <ThemeBuilderModal
            colorFields={CUSTOM_COLOR_FIELDS}
            name={editNameDraft}
            onNameChange={setEditNameDraft}
            colors={editColorsDraft}
            onColorChange={handleEditColorChange}
            highlightedField={highlightedField}
            onHighlight={setHighlightedField}
            error={themeError}
            saving={savingThemeEdit}
            onSave={handleSaveThemeEdit}
            onCancel={closeEditor}
          />
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

        <hr className="modal-divider" />

        <div className="modal-field-label">Active sessions</div>
        {sessionsError && <p className="modal-error">{sessionsError}</p>}
        {sessions.length === 0 ? (
          <p className="modal-empty">No active sessions.</p>
        ) : (
          sessions.map((session) => (
            <div key={session.id} className="modal-list-row">
              <div className="modal-list-row-body">
                <div className="modal-list-row-title">
                  {session.device_label}
                  {session.is_current && ' · This device'}
                </div>
                <div className="modal-list-row-sub">
                  {session.ip_address ?? 'Unknown location'} · last active{' '}
                  {new Date(session.last_seen_at).toLocaleString()}
                </div>
              </div>
              <button
                type="button"
                className="modal-list-row-action"
                disabled={revokingSessionId === session.id}
                onClick={() => handleRevokeSession(session)}
              >
                {session.is_current ? 'Sign out' : 'Revoke'}
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

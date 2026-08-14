import { useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { removeAvatar, updateProfile, uploadAvatar } from '../api/auth'
import { ApiError } from '../api/client'
import { getUserAvatarUrl } from '../api/users'
import { useAuth } from '../context/AuthContext'
import { hashIndex } from '../lib/avatar'
import { UserAvatar } from './UserAvatar'
import './Modal.css'

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
      </div>
    </div>
  )
}

import { useState, type ChangeEvent, type FormEvent } from 'react'
import { uploadCustomEmoji } from '../api/customEmoji'
import { ApiError } from '../api/client'
import { EMOJI_SHORTCODES } from '../lib/emojiShortcodes'
import './Modal.css'

interface CustomEmojiUploadModalProps {
  onClose: () => void
  onUploaded: () => void
}

// Mirrors the shortcode charset the backend actually enforces (see
// backend/app/services/custom_emoji_service.py's SHORTCODE_PATTERN) --
// checked here too so a bad name shows up immediately next to the field
// instead of only after a round trip.
const SHORTCODE_PATTERN = /^[a-z0-9_-]{2,30}$/

export function CustomEmojiUploadModal({ onClose, onUploaded }: CustomEmojiUploadModalProps) {
  const [shortcode, setShortcode] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function handleFileSelected(e: ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setFile(selected)
    setPreviewUrl(selected ? URL.createObjectURL(selected) : null)
  }

  function handleClose() {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    onClose()
  }

  const normalizedShortcode = shortcode.trim().toLowerCase()
  const shortcodeValid = SHORTCODE_PATTERN.test(normalizedShortcode)
  // A built-in shortcode always wins when :name: is typed in a message
  // (see MessageContent.tsx's convertShortcodes, which runs first) -- a
  // custom emoji uploaded under a colliding name would still upload fine,
  // but could never actually be *reached* by typing its shortcode. Not a
  // hard block (site-admin-free upload means no server-side authority to
  // enforce this against ~950 names), just steered away from here.
  const collidesWithBuiltin = shortcodeValid && normalizedShortcode in EMOJI_SHORTCODES

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!file || !shortcodeValid) return
    setSubmitting(true)
    setError(null)
    try {
      await uploadCustomEmoji(normalizedShortcode, file)
      onUploaded()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-scrim" onClick={handleClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Add custom emoji</h2>
          <button type="button" className="modal-close" onClick={handleClose} aria-label="Close">
            &times;
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-field-label">Shortcode</div>
          <input
            type="text"
            value={shortcode}
            onChange={(e) => setShortcode(e.target.value)}
            placeholder="party-parrot"
            autoFocus
          />
          {shortcode && !shortcodeValid && (
            <p className="modal-error">
              2-30 characters: lowercase letters, numbers, hyphens, underscores
            </p>
          )}
          {collidesWithBuiltin && (
            <p className="modal-error">
              :{normalizedShortcode}: is already a built-in emoji -- typing it will always show that
              one instead of yours
            </p>
          )}
          <div className="modal-field-label">Image</div>
          <input type="file" accept="image/png,image/jpeg,image/gif,image/webp" onChange={handleFileSelected} />
          {previewUrl && (
            <img src={previewUrl} alt="Preview" className="custom-emoji-upload-preview" />
          )}
          {error && <p className="modal-error">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={handleClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={submitting || !file || !shortcodeValid}>
              {submitting ? 'Uploading…' : 'Add emoji'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

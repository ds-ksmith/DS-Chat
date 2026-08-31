import { useState } from 'react'
import { deleteCustomEmoji } from '../api/customEmoji'
import { useAuth } from '../context/AuthContext'
import { useCustomEmoji } from '../context/CustomEmojiContext'
import type { CustomEmoji } from '../types'
import { CustomEmojiUploadModal } from './CustomEmojiUploadModal'
import { EmojiGlyph } from './MessageContent'
import './Modal.css'

interface CustomEmojiManageModalProps {
  onClose: () => void
}

// Moved out of the reaction/composer emoji picker -- that grid packs items
// 9-to-a-row with a delete "x" overlapping the glyph itself, which on a
// touch screen is far too easy to hit by accident while just trying to
// react. A dedicated list with a normal-sized "Delete" button (plus the
// same confirm() every other destructive action in this app uses) needs a
// deliberate tap to actually delete something.
export function CustomEmojiManageModal({ onClose }: CustomEmojiManageModalProps) {
  const { user } = useAuth()
  const { list, refresh } = useCustomEmoji()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  async function handleDelete(emoji: CustomEmoji) {
    if (!confirm(`Delete :${emoji.shortcode}:? This can't be undone.`)) return
    setDeletingId(emoji.id)
    try {
      await deleteCustomEmoji(emoji.id)
      await refresh()
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Custom emoji</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="modal-field-label">Site emoji</div>
        {list.length === 0 ? (
          <p className="modal-empty">No custom emoji yet.</p>
        ) : (
          list.map((emoji) => {
            const canDelete = user?.id === emoji.uploaded_by || user?.is_site_admin
            return (
              <div key={emoji.id} className="modal-list-row">
                <div className="modal-list-row-body">
                  <div className="modal-list-row-title">
                    <EmojiGlyph value={`:${emoji.shortcode}:`} /> :{emoji.shortcode}:
                  </div>
                  <div className="modal-list-row-sub">
                    Added {new Date(emoji.created_at).toLocaleDateString()}
                  </div>
                </div>
                {canDelete && (
                  <button
                    type="button"
                    className="modal-list-row-action"
                    disabled={deletingId === emoji.id}
                    onClick={() => handleDelete(emoji)}
                  >
                    {deletingId === emoji.id ? 'Deleting…' : 'Delete'}
                  </button>
                )}
              </div>
            )
          })
        )}

        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close
          </button>
          <button type="button" className="btn-primary" onClick={() => setUploadOpen(true)}>
            Add emoji
          </button>
        </div>
      </div>

      {uploadOpen && (
        <CustomEmojiUploadModal
          onClose={() => setUploadOpen(false)}
          onUploaded={() => {
            refresh()
            setUploadOpen(false)
          }}
        />
      )}
    </div>
  )
}

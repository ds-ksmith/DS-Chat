import { useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { uploadRoomFile, uploadRoomImage } from '../api/rooms'
import { getUploadLimit } from '../api/uploads'
import { formatFileSize } from '../lib/fileSize'
import { EmojiPicker } from './EmojiPicker'
import './Composer.css'

interface ComposerProps {
  roomId: string
  roomName: string
  disabled?: boolean
  onSend: (content: string, imageId?: string, fileId?: string) => void
}


export function Composer({ roomId, roomName, disabled, onSend }: ComposerProps) {
  const [value, setValue] = useState('')
  const [pendingImage, setPendingImage] = useState<{ id: string; previewUrl: string } | null>(null)
  const [pendingFile, setPendingFile] = useState<{ id: string; filename: string; size: number } | null>(
    null,
  )
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false)
  const [maxUploadBytes, setMaxUploadBytes] = useState<number | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const online = useOnlineStatus()

  useEffect(() => {
    getUploadLimit()
      .then((limit) => setMaxUploadBytes(limit.max_upload_bytes))
      .catch(() => {
        // Non-critical -- if this fails, oversized uploads just get caught
        // by the server's 413 instead of client-side, no functional loss.
      })
  }, [])

  function autoGrow() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }

  function handleSend() {
    const trimmed = value.trim()
    if (!trimmed && !pendingImage && !pendingFile) return
    onSend(trimmed, pendingImage?.id, pendingFile?.id)
    setValue('')
    removePendingImage()
    setPendingFile(null)
    requestAnimationFrame(autoGrow)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  async function handleFileSelected(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return

    setUploadError(null)

    if (maxUploadBytes !== null && file.size > maxUploadBytes) {
      setUploadError(`File exceeds ${formatFileSize(maxUploadBytes)} limit`)
      return
    }

    setUploading(true)
    try {
      if (file.type.startsWith('image/')) {
        const { id } = await uploadRoomImage(roomId, file)
        setPendingImage((prev) => {
          if (prev) URL.revokeObjectURL(prev.previewUrl)
          return { id, previewUrl: URL.createObjectURL(file) }
        })
      } else {
        const uploaded = await uploadRoomFile(roomId, file)
        setPendingFile({ id: uploaded.id, filename: uploaded.filename, size: uploaded.size_bytes })
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  function removePendingImage() {
    setPendingImage((prev) => {
      if (prev) URL.revokeObjectURL(prev.previewUrl)
      return null
    })
  }

  function insertEmoji(emoji: string) {
    const el = textareaRef.current
    setEmojiPickerOpen(false)
    if (!el) {
      setValue((v) => v + emoji)
      return
    }
    const start = el.selectionStart ?? value.length
    const end = el.selectionEnd ?? value.length
    setValue(value.slice(0, start) + emoji + value.slice(end))
    requestAnimationFrame(() => {
      el.focus()
      const cursor = start + emoji.length
      el.setSelectionRange(cursor, cursor)
      autoGrow()
    })
  }

  return (
    <div className="composer">
      {pendingImage && (
        <div className="composer-attachment">
          <img src={pendingImage.previewUrl} alt="" className="composer-attachment-thumb" />
          <button
            type="button"
            className="composer-attachment-remove"
            onClick={removePendingImage}
            aria-label="Remove attached image"
          >
            ×
          </button>
        </div>
      )}
      {pendingFile && (
        <div className="composer-attachment composer-attachment-file">
          <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path
              d="M6 2.5h6l4 4V16a1.5 1.5 0 0 1-1.5 1.5h-8A1.5 1.5 0 0 1 5 16V4A1.5 1.5 0 0 1 6 2.5Z"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinejoin="round"
            />
            <path d="M12 2.5V6a1 1 0 0 0 1 1h3.5" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
          </svg>
          <span className="composer-attachment-filename">{pendingFile.filename}</span>
          <span className="composer-attachment-size">{formatFileSize(pendingFile.size)}</span>
          <button
            type="button"
            className="composer-attachment-remove"
            onClick={() => setPendingFile(null)}
            aria-label="Remove attached file"
          >
            ×
          </button>
        </div>
      )}
      {uploadError && <div className="composer-status composer-error">{uploadError}</div>}
      <div className="composer-box">
        <input
          ref={fileInputRef}
          type="file"
          className="composer-file-input"
          onChange={handleFileSelected}
        />
        <button
          type="button"
          className="composer-attach"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || uploading}
          aria-label="Attach a file"
        >
          {uploading ? (
            <svg className="composer-spinner" width="15" height="15" viewBox="0 0 20 20" aria-hidden="true">
              <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="2.4" fill="none" strokeDasharray="30 14" />
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path
                d="M13.5 6.5 8 12a2.1 2.1 0 0 0 3 3l5.5-5.5a4 4 0 0 0-5.7-5.7L4.8 9.8a5.7 5.7 0 0 0 8 8"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </button>
        <div className="composer-emoji-wrap">
          <button
            type="button"
            className="composer-emoji-trigger"
            onClick={() => setEmojiPickerOpen((v) => !v)}
            disabled={disabled}
            aria-label="Insert an emoji"
          >
            🙂
          </button>
          {emojiPickerOpen && (
            <EmojiPicker
              onPick={insertEmoji}
              onClose={() => setEmojiPickerOpen(false)}
              placement="above"
              align="left"
            />
          )}
        </div>
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          disabled={disabled}
          onChange={(e) => {
            setValue(e.target.value)
            autoGrow()
          }}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? (online ? 'Connecting…' : "You're offline") : `Message #${roomName}`}
          spellCheck
        />
        <button
          type="button"
          className="composer-send"
          onClick={handleSend}
          disabled={disabled || (!value.trim() && !pendingImage && !pendingFile)}
          aria-label="Send message"
        >
          <svg width="15" height="15" viewBox="0 0 20 20" aria-hidden="true">
            <polygon points="2,2 18,10 2,18 6,10" fill="currentColor" />
          </svg>
        </button>
      </div>
      {disabled && (
        <div className="composer-status">{online ? 'Connecting…' : "You're offline — messages can't be sent right now"}</div>
      )}
    </div>
  )
}

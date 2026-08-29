import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
  type KeyboardEvent,
} from 'react'
import { useEscapeKey } from '../hooks/useEscapeKey'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { uploadRoomFile, uploadRoomImage } from '../api/rooms'
import { getUploadLimit } from '../api/uploads'
import { useCustomEmoji } from '../context/CustomEmojiContext'
import { EMOJI_SHORTCODES, SHORTCODE_BY_GLYPH } from '../lib/emojiShortcodes'
import { formatFileSize } from '../lib/fileSize'
import { getRecentEmoji, recordEmojiUsed } from '../lib/recentEmoji'
import type { MyRoomItem, RoomMember } from '../types'
import { EmojiPicker } from './EmojiPicker'
import { EmojiShortcodeAutocomplete, type EmojiShortcodeMatch } from './EmojiShortcodeAutocomplete'
import { MentionAutocomplete } from './MentionAutocomplete'
import { RoomReferenceAutocomplete } from './RoomReferenceAutocomplete'
import './Composer.css'

interface ComposerProps {
  roomId: string
  roomName: string
  isDm?: boolean
  members: RoomMember[]
  // #47: rooms this user belongs to, for the #roomname autocomplete --
  // deliberately the same list ChatPane already resolves message-display
  // references against (see its myRooms comment), so what autocompletes
  // while typing and what actually renders as a link later agree.
  rooms: MyRoomItem[]
  disabled?: boolean
  // #57: an archived room is permanently read-only, not just transiently
  // disconnected -- kept as its own prop rather than folded into `disabled`
  // so the placeholder/status text can say why, instead of the connecting/
  // offline copy below (which would be actively misleading here: waiting
  // won't ever re-enable this).
  archived?: boolean
  onSend: (content: string, imageId?: string, fileId?: string) => void
}

interface TriggerQuery {
  start: number
  end: number
  text: string
}

// Scans left from the cursor for an active "<trigger>partial" token -- the
// trigger char not preceded by a word character (so "foo@bar" mid-email
// doesn't trigger a mention query, and a literal '#' inside a word doesn't
// trigger a room-reference one) with only identifier-safe characters
// between it and the cursor (a space breaks out of the query entirely,
// closing the dropdown). Shared by both @mention and #roomname detection --
// only the trigger character differs.
function detectTriggerQuery(text: string, cursor: number, trigger: string): TriggerQuery | null {
  let i = cursor - 1
  while (i >= 0 && /[a-zA-Z0-9_.-]/.test(text[i])) i--
  if (i < 0 || text[i] !== trigger) return null
  const prevChar = text[i - 1]
  if (prevChar && /\w/.test(prevChar)) return null
  return { start: i, end: cursor, text: text.slice(i + 1, cursor) }
}

function detectMentionQuery(text: string, cursor: number): TriggerQuery | null {
  return detectTriggerQuery(text, cursor, '@')
}

function detectRoomReferenceQuery(text: string, cursor: number): TriggerQuery | null {
  return detectTriggerQuery(text, cursor, '#')
}

// #54: a dedicated scan rather than detectTriggerQuery(text, cursor, ':')
// -- shortcode names (see emojiShortcodes.ts) can contain '+'/'-' (':+1:',
// ':t-rex:') but never '.', the reverse of what the shared @/# charset
// allows, so it doesn't fit that helper's single fixed charset.
function detectEmojiQuery(text: string, cursor: number): TriggerQuery | null {
  let i = cursor - 1
  while (i >= 0 && /[a-zA-Z0-9_+-]/.test(text[i])) i--
  if (i < 0 || text[i] !== ':') return null
  const prevChar = text[i - 1]
  if (prevChar && /\w/.test(prevChar)) return null
  return { start: i, end: cursor, text: text.slice(i + 1, cursor) }
}

interface AttachMenuProps {
  onPickPhoto: () => void
  onPickFile: () => void
  onClose: () => void
}

// #29: splits into two explicit choices rather than one unrestricted file
// input -- see photoInputRef's comment on the Composer below for why a
// single input can't reliably offer both "any file type" and a mobile
// gallery shortcut at once.
function AttachMenu({ onPickPhoto, onPickFile, onClose }: AttachMenuProps) {
  useEscapeKey(onClose)
  return (
    <>
      <div className="composer-attach-menu-scrim" onClick={onClose} />
      <div className="composer-attach-menu" role="menu">
        <button type="button" role="menuitem" onClick={onPickPhoto}>
          Photo or video
        </button>
        <button type="button" role="menuitem" onClick={onPickFile}>
          File
        </button>
      </div>
    </>
  )
}

export function Composer({ roomId, roomName, isDm, members, rooms, disabled, archived, onSend }: ComposerProps) {
  // Every gate below (attach/emoji buttons, textarea, send button) reads
  // this instead of the raw `disabled` prop -- an archived room must be
  // just as unwritable as a disconnected one, it just says why differently
  // (see the placeholder/status text further down).
  const isDisabled = disabled || archived
  const [value, setValue] = useState('')
  const [pendingImage, setPendingImage] = useState<{ id: string; previewUrl: string } | null>(null)
  const [pendingFile, setPendingFile] = useState<{ id: string; filename: string; size: number } | null>(
    null,
  )
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false)
  const [maxUploadBytes, setMaxUploadBytes] = useState<number | null>(null)
  const [mentionQuery, setMentionQuery] = useState<TriggerQuery | null>(null)
  const [mentionActiveIndex, setMentionActiveIndex] = useState(0)
  const [roomQuery, setRoomQuery] = useState<TriggerQuery | null>(null)
  const [roomActiveIndex, setRoomActiveIndex] = useState(0)
  const [emojiQuery, setEmojiQuery] = useState<TriggerQuery | null>(null)
  const [emojiActiveIndex, setEmojiActiveIndex] = useState(0)
  const [dragActive, setDragActive] = useState(false)
  const [attachMenuOpen, setAttachMenuOpen] = useState(false)
  const { byShortcode: customEmojiByShortcode } = useCustomEmoji()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // #29: a separate input with an image/video accept hint, so mobile
  // browsers offer their media picker (with a direct Photos/Gallery
  // shortcut) instead of the generic chooser a fully-unrestricted `accept`
  // falls back to (Camera / Camera Video / Files, no gallery). The
  // unrestricted `fileInputRef` above still exists for the "File" choice --
  // Android can't reliably offer both a gallery shortcut and "any file
  // type" from a single input, so the attach button now opens a small menu
  // to pick which one you want first.
  const photoInputRef = useRef<HTMLInputElement>(null)
  // Counts nested dragenter/dragleave pairs (the overlay, the composer box,
  // the textarea are all separate elements a drag passes over) so the
  // highlight doesn't flicker off every time the pointer crosses a child
  // element boundary -- only actually leaving the whole composer zeroes it.
  const dragCounterRef = useRef(0)
  const online = useOnlineStatus()

  const mentionMatches = useMemo(() => {
    if (!mentionQuery) return []
    const q = mentionQuery.text.toLowerCase()
    return members.filter((m) => m.username.toLowerCase().startsWith(q)).slice(0, 8)
  }, [mentionQuery, members])

  const roomMatches = useMemo(() => {
    if (!roomQuery) return []
    const q = roomQuery.text.toLowerCase()
    return rooms.filter((r) => r.name.toLowerCase().startsWith(q)).slice(0, 8)
  }, [roomQuery, rooms])

  const emojiMatches = useMemo((): EmojiShortcodeMatch[] => {
    if (!emojiQuery) return []
    const q = emojiQuery.text.toLowerCase()
    // A bare ":" with nothing typed yet -- suggest recently-used emoji
    // (already capped to 8, see recentEmoji.ts) rather than an arbitrary
    // slice of the ~950 known shortcodes. A recent custom-emoji pick is
    // stored as its literal `:shortcode:` (see recordEmojiUsed's call
    // sites) -- resolved against the live registry the same way, so a
    // since-deleted one just doesn't show up here.
    if (!q) {
      return getRecentEmoji()
        .map((value) => {
          const customMatch = /^:([a-z0-9_-]+):$/.exec(value)
          if (customMatch && customEmojiByShortcode.has(customMatch[1])) {
            return { shortcode: customMatch[1], glyph: null }
          }
          const shortcode = SHORTCODE_BY_GLYPH[value]
          return shortcode ? { shortcode, glyph: value } : null
        })
        .filter((match): match is EmojiShortcodeMatch => match !== null)
    }
    // Custom emoji surface first -- a smaller, more specific set, and the
    // whole reason this app has an upload feature at all is for them to be
    // reachable as easily as the built-in set.
    const customMatches: EmojiShortcodeMatch[] = [...customEmojiByShortcode.keys()]
      .filter((shortcode) => shortcode.startsWith(q))
      .map((shortcode) => ({ shortcode, glyph: null }))
    const builtinMatches: EmojiShortcodeMatch[] = Object.keys(EMOJI_SHORTCODES)
      .filter((shortcode) => shortcode.startsWith(q))
      .map((shortcode) => ({ shortcode, glyph: EMOJI_SHORTCODES[shortcode] }))
    return [...customMatches, ...builtinMatches].slice(0, 8)
  }, [emojiQuery, customEmojiByShortcode])

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
    setMentionQuery(null)
    setRoomQuery(null)
    setEmojiQuery(null)
    removePendingImage()
    setPendingFile(null)
    requestAnimationFrame(autoGrow)
  }

  function selectMention(username: string) {
    const query = mentionQuery
    if (!query) return
    const el = textareaRef.current
    const next = value.slice(0, query.start) + '@' + username + ' ' + value.slice(query.end)
    setValue(next)
    setMentionQuery(null)
    requestAnimationFrame(() => {
      if (!el) return
      el.focus()
      const cursor = query.start + username.length + 2 // '@' + username + trailing space
      el.setSelectionRange(cursor, cursor)
      autoGrow()
    })
  }

  function selectRoomReference(roomName: string) {
    const query = roomQuery
    if (!query) return
    const el = textareaRef.current
    const next = value.slice(0, query.start) + '#' + roomName + ' ' + value.slice(query.end)
    setValue(next)
    setRoomQuery(null)
    requestAnimationFrame(() => {
      if (!el) return
      el.focus()
      const cursor = query.start + roomName.length + 2 // '#' + roomName + trailing space
      el.setSelectionRange(cursor, cursor)
      autoGrow()
    })
  }

  function selectEmojiShortcode(shortcode: string) {
    const query = emojiQuery
    if (!query) return
    // A custom emoji has no unicode glyph to substitute -- its literal
    // `:shortcode:` text is what actually gets stored/rendered (see
    // MessageContent.tsx's convertCustomEmojiShortcodes), so that's what
    // goes in the textarea instead of a glyph.
    const isCustom = customEmojiByShortcode.has(shortcode)
    const glyph = EMOJI_SHORTCODES[shortcode]
    if (!isCustom && !glyph) return
    const inserted = isCustom ? `:${shortcode}:` : glyph
    // Matches EmojiPicker's own insertEmoji -- a shortcode-completed emoji
    // counts as "used" the same as one picked from the picker, so it
    // shows up there too next time.
    recordEmojiUsed(inserted)
    const el = textareaRef.current
    const next = value.slice(0, query.start) + inserted + ' ' + value.slice(query.end)
    setValue(next)
    setEmojiQuery(null)
    requestAnimationFrame(() => {
      if (!el) return
      el.focus()
      const cursor = query.start + inserted.length + 1 // inserted text + trailing space
      el.setSelectionRange(cursor, cursor)
      autoGrow()
    })
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (mentionQuery && mentionMatches.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setMentionActiveIndex((i) => (i + 1) % mentionMatches.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setMentionActiveIndex((i) => (i - 1 + mentionMatches.length) % mentionMatches.length)
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        selectMention(mentionMatches[mentionActiveIndex].username)
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setMentionQuery(null)
        return
      }
    }
    if (roomQuery && roomMatches.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setRoomActiveIndex((i) => (i + 1) % roomMatches.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setRoomActiveIndex((i) => (i - 1 + roomMatches.length) % roomMatches.length)
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        selectRoomReference(roomMatches[roomActiveIndex].name)
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setRoomQuery(null)
        return
      }
    }
    if (emojiQuery && emojiMatches.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setEmojiActiveIndex((i) => (i + 1) % emojiMatches.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setEmojiActiveIndex((i) => (i - 1 + emojiMatches.length) % emojiMatches.length)
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        selectEmojiShortcode(emojiMatches[emojiActiveIndex].shortcode)
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setEmojiQuery(null)
        return
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Re-detects the active @/# query on every cursor move, not just typing --
  // React's onSelect fires for clicks and arrow-key navigation too, so
  // moving the cursor out of a partial mention/reference (without deleting
  // it) still correctly closes the dropdown.
  function handleSelectionChange(e: FormEvent<HTMLTextAreaElement>) {
    const el = e.currentTarget
    const cursor = el.selectionStart ?? 0
    setMentionQuery(detectMentionQuery(el.value, cursor))
    setMentionActiveIndex(0)
    setRoomQuery(detectRoomReferenceQuery(el.value, cursor))
    setRoomActiveIndex(0)
    setEmojiQuery(detectEmojiQuery(el.value, cursor))
    setEmojiActiveIndex(0)
  }

  async function handleFile(file: File) {
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

  function handleFileSelected(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (file) handleFile(file)
  }

  function handleDragEnter(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    if (isDisabled) return
    dragCounterRef.current++
    setDragActive(true)
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    dragCounterRef.current = Math.max(0, dragCounterRef.current - 1)
    if (dragCounterRef.current === 0) setDragActive(false)
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    // Required even though it does nothing else -- without preventDefault()
    // here, the browser rejects the element as a drop target entirely and
    // handleDrop never fires (it just navigates to/opens the dropped file).
    e.preventDefault()
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    dragCounterRef.current = 0
    setDragActive(false)
    if (isDisabled) return
    // Only the first dropped file, matching the existing single-attachment-
    // per-message limit (the button-triggered file input isn't `multiple`
    // either).
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
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
    <div
      className="composer"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {dragActive && (
        <div className="composer-drop-overlay">
          <span>Drop to attach</span>
        </div>
      )}
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
          ref={photoInputRef}
          type="file"
          accept="image/*,video/*"
          className="composer-file-input"
          onChange={handleFileSelected}
        />
        <input
          ref={fileInputRef}
          type="file"
          className="composer-file-input"
          onChange={handleFileSelected}
        />
        <div className="composer-attach-wrap">
          <button
            type="button"
            className="composer-attach"
            onClick={() => setAttachMenuOpen((v) => !v)}
            disabled={isDisabled || uploading}
            aria-label="Attach a photo or file"
            aria-expanded={attachMenuOpen}
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
          {attachMenuOpen && (
            <AttachMenu
              onPickPhoto={() => {
                setAttachMenuOpen(false)
                photoInputRef.current?.click()
              }}
              onPickFile={() => {
                setAttachMenuOpen(false)
                fileInputRef.current?.click()
              }}
              onClose={() => setAttachMenuOpen(false)}
            />
          )}
        </div>
        <div className="composer-emoji-wrap">
          <button
            type="button"
            className="composer-emoji-trigger"
            onClick={() => setEmojiPickerOpen((v) => !v)}
            disabled={isDisabled}
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
        <div className="composer-textarea-wrap">
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            disabled={isDisabled}
            onChange={(e) => {
              setValue(e.target.value)
              autoGrow()
              const cursor = e.target.selectionStart ?? 0
              setMentionQuery(detectMentionQuery(e.target.value, cursor))
              setMentionActiveIndex(0)
              setRoomQuery(detectRoomReferenceQuery(e.target.value, cursor))
              setRoomActiveIndex(0)
              setEmojiQuery(detectEmojiQuery(e.target.value, cursor))
              setEmojiActiveIndex(0)
            }}
            onSelect={handleSelectionChange}
            onKeyDown={handleKeyDown}
            placeholder={
              archived
                ? 'This room has been archived'
                : disabled
                  ? online
                    ? 'Connecting…'
                    : "You're offline"
                  : `Message ${isDm ? roomName : `#${roomName}`}`
            }
            spellCheck
          />
          {mentionQuery && mentionMatches.length > 0 && (
            <MentionAutocomplete
              matches={mentionMatches}
              activeIndex={mentionActiveIndex}
              onPick={selectMention}
              onHover={setMentionActiveIndex}
            />
          )}
          {roomQuery && roomMatches.length > 0 && (
            <RoomReferenceAutocomplete
              matches={roomMatches}
              activeIndex={roomActiveIndex}
              onPick={selectRoomReference}
              onHover={setRoomActiveIndex}
            />
          )}
          {emojiQuery && emojiMatches.length > 0 && (
            <EmojiShortcodeAutocomplete
              matches={emojiMatches}
              activeIndex={emojiActiveIndex}
              onPick={selectEmojiShortcode}
              onHover={setEmojiActiveIndex}
            />
          )}
        </div>
        <button
          type="button"
          className="composer-send"
          onClick={handleSend}
          disabled={isDisabled || (!value.trim() && !pendingImage && !pendingFile)}
          aria-label="Send message"
        >
          <svg width="15" height="15" viewBox="0 0 20 20" aria-hidden="true">
            <polygon points="2,2 18,10 2,18 6,10" fill="currentColor" />
          </svg>
        </button>
      </div>
      {archived ? (
        <div className="composer-status">This room has been archived and is read-only</div>
      ) : (
        disabled && (
          <div className="composer-status">{online ? 'Connecting…' : "You're offline — messages can't be sent right now"}</div>
        )
      )}
    </div>
  )
}

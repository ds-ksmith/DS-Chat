import { useEffect, useMemo, useRef, useState } from 'react'
import { getRoomFileUrl, getRoomImageUrl } from '../api/rooms'
import { useAuth } from '../context/AuthContext'
import { formatFileSize } from '../lib/fileSize'
import { avatarUrlFor, displayNameFor, senderColorIndex, statusFor } from '../lib/messageGrouping'
import type { ChatMessageEnvelope, Message, MessageFileInfo, RoomMember } from '../types'
import { EMOJI_PICKER_MAX_HEIGHT, EmojiPicker } from './EmojiPicker'
import { FilePreviewModal, getPreviewKind } from './FilePreviewModal'
import { ImageLightbox } from './ImageLightbox'
import { LinkPreviewCard } from './LinkPreviewCard'
import { MessageContent } from './MessageContent'
import { UserAvatar } from './UserAvatar'
import { VideoLightbox } from './VideoLightbox'
import './MessageList.css'

export function FileAttachmentIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path
        d="M6 2.5h6l4 4V16a1.5 1.5 0 0 1-1.5 1.5h-8A1.5 1.5 0 0 1 5 16V4A1.5 1.5 0 0 1 6 2.5Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path d="M12 2.5V6a1 1 0 0 0 1 1h3.5" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  )
}

interface FileAttachmentCardProps {
  file: MessageFileInfo
  roomId: string
  onPreview: () => void
}

// Previewable files (markdown/text) open a modal on click, with a small
// explicit download icon alongside; everything else keeps the original
// click-to-download behavior unchanged.
function FileAttachmentCard({ file, roomId, onPreview }: FileAttachmentCardProps) {
  const info = (
    <span className="message-file-info">
      <span className="message-file-name">{file.filename}</span>
      <span className="message-file-size">{formatFileSize(file.size_bytes)}</span>
    </span>
  )

  if (getPreviewKind(file.filename)) {
    return (
      <button type="button" className="message-file-attachment" onClick={onPreview}>
        <FileAttachmentIcon />
        {info}
      </button>
    )
  }

  return (
    <a href={getRoomFileUrl(roomId, file.id)} download={file.filename} className="message-file-attachment">
      <FileAttachmentIcon />
      {info}
    </a>
  )
}

// #65: kept in sync with backend/app/storage.py's INLINE_SAFE_VIDEO_
// CONTENT_TYPES -- the server only ever serves these particular content
// types without a forced download, so a <video> tag pointed at anything
// else would just show a broken player instead of playing (or, worse,
// trigger a download the moment the browser tries to fetch it).
const PLAYABLE_VIDEO_CONTENT_TYPES = new Set(['video/mp4', 'video/webm', 'video/ogg'])

interface VideoAttachmentProps {
  file: MessageFileInfo
  roomId: string
  onExpand: () => void
}

// Plays inline via the browser's own <video controls> (no custom overlay
// needed for play/pause/volume/seek) -- the one thing it doesn't give a
// small inline player is an obvious way to go bigger. The expand button
// opens a VideoLightbox (matching how images already expand) rather than
// calling the Fullscreen API directly on the video element -- that API is
// unreliable in embedded/packaged contexts (e.g. the Electron desktop
// build), where a rejected requestFullscreen() promise just does nothing
// with no visible error.
function VideoAttachment({ file, roomId, onExpand }: VideoAttachmentProps) {
  return (
    <div className="message-video-wrap">
      <video src={getRoomFileUrl(roomId, file.id)} controls className="message-video" />
      <button
        type="button"
        className="message-video-expand"
        onClick={onExpand}
        aria-label="Expand video"
      >
        <svg width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path
            d="M7 3H3v4M13 3h4v4M3 13v4h4M17 13v4h-4"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  )
}

interface MessageListProps {
  roomId: string
  messages: (Message | ChatMessageEnvelope)[]
  members: RoomMember[]
  myRooms: Map<string, string>
  onEdit: (messageId: string, content: string) => void
  onReact: (messageId: string, emoji: string) => void
  onDelete: (messageId: string) => void
}

export function MessageList({
  roomId,
  messages,
  members,
  myRooms,
  onEdit,
  onReact,
  onDelete,
}: MessageListProps) {
  const { user } = useAuth()
  const containerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  // Whether the view should be pinned to the latest message -- true right
  // after a room switch/new message, flipped off if the user deliberately
  // scrolls away from the bottom. Read by the image-load handler below so a
  // late-loading image doesn't yank someone back down mid-scrollback.
  const pinnedToBottomRef = useRef(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
  const [videoLightbox, setVideoLightbox] = useState<{ src: string; filename: string } | null>(null)
  const [reactingId, setReactingId] = useState<string | null>(null)
  const [reactionPlacement, setReactionPlacement] = useState<'above' | 'below'>('below')
  const [previewFile, setPreviewFile] = useState<MessageFileInfo | null>(null)
  const memberUsernames = useMemo(() => new Set(members.map((m) => m.username)), [members])

  function displayNameForUserId(userId: string): string {
    const member = members.find((m) => m.user_id === userId)
    return member?.display_name || member?.username || 'someone'
  }

  useEffect(() => {
    pinnedToBottomRef.current = true
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [roomId, messages.length])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    function handleScroll() {
      if (!container) return
      // Within 48px of the true bottom counts as "at the bottom" -- an
      // exact-equality check would drop pinning from sub-pixel scroll
      // rounding alone.
      pinnedToBottomRef.current =
        container.scrollHeight - container.scrollTop - container.clientHeight < 48
    }
    // `load` doesn't bubble, but a capture-phase listener on an ancestor
    // still sees it fire on the way down -- lets one listener catch every
    // image in the list (message attachments and link-preview thumbnails
    // alike) without wiring an onLoad prop through each of them.
    function handleContentGrow() {
      if (pinnedToBottomRef.current) bottomRef.current?.scrollIntoView({ block: 'end' })
    }
    container.addEventListener('scroll', handleScroll, { passive: true })
    container.addEventListener('load', handleContentGrow, true)
    return () => {
      container.removeEventListener('scroll', handleScroll)
      container.removeEventListener('load', handleContentGrow, true)
    }
  }, [])

  function startEdit(msg: Message | ChatMessageEnvelope) {
    setEditingId(msg.id)
    setDraft(msg.content ?? '')
  }

  function commitEdit(messageId: string) {
    const trimmed = draft.trim()
    if (trimmed) onEdit(messageId, trimmed)
    setEditingId(null)
  }

  function handleDelete(messageId: string) {
    // Matches the confirm() pattern already used for other destructive
    // actions in this app (RoomInfoPanel's leave/delete-room,
    // ProfileModal's delete-theme) rather than a custom dialog.
    if (!confirm("Delete this message? This can't be undone.")) return
    onDelete(messageId)
  }

  return (
    <div className="message-list" ref={containerRef}>
      {messages.map((msg, i) => {
        const mine = msg.user_id === user?.id
        const prev = messages[i - 1]
        // Mattermost-style grouping: every message shows who sent it, but
        // consecutive messages from the same sender only repeat the
        // avatar/name/timestamp header on the first one in the run --
        // applies uniformly, including to your own messages.
        const isGroupStart = !prev || prev.user_id !== msg.user_id
        const editing = editingId === msg.id
        const deleted = !!msg.deleted_at

        return (
          <div key={msg.id} className={`message-row${isGroupStart ? ' message-row-start' : ''}`}>
            <div className="message-avatar-slot">
              {isGroupStart && (
                <UserAvatar
                  username={msg.username}
                  colorIndex={senderColorIndex(msg.username, members)}
                  avatarUrl={avatarUrlFor(msg.username, members)}
                  status={statusFor(msg.username, members)}
                />
              )}
            </div>
            <div className="message-content">
              {isGroupStart && (
                <div className="message-header">
                  <span className="message-author">{displayNameFor(msg.username, members)}</span>
                  <span className="message-time">
                    {new Date(msg.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                  </span>
                </div>
              )}
              {deleted ? (
                <div className="message-text message-deleted-text">
                  <em>This message was deleted</em>
                </div>
              ) : editing ? (
                <textarea
                  autoFocus
                  rows={Math.min(10, draft.split('\n').length)}
                  className="message-edit-input"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      commitEdit(msg.id)
                    }
                    if (e.key === 'Escape') setEditingId(null)
                  }}
                  onBlur={() => commitEdit(msg.id)}
                  spellCheck
                />
              ) : (
                <>
                  {msg.image_id && (
                    <img
                      src={getRoomImageUrl(roomId, msg.image_id)}
                      alt=""
                      className="message-image"
                      onClick={() => setLightboxSrc(getRoomImageUrl(roomId, msg.image_id!))}
                    />
                  )}
                  {msg.file && PLAYABLE_VIDEO_CONTENT_TYPES.has(msg.file.content_type) && (
                    <VideoAttachment
                      file={msg.file}
                      roomId={roomId}
                      onExpand={() =>
                        setVideoLightbox({
                          src: getRoomFileUrl(roomId, msg.file!.id),
                          filename: msg.file!.filename,
                        })
                      }
                    />
                  )}
                  {msg.file && !PLAYABLE_VIDEO_CONTENT_TYPES.has(msg.file.content_type) && (
                    <FileAttachmentCard
                      file={msg.file}
                      roomId={roomId}
                      onPreview={() => setPreviewFile(msg.file!)}
                    />
                  )}
                  {msg.content && (
                    <div className="message-text">
                      <MessageContent content={msg.content} memberUsernames={memberUsernames} myRooms={myRooms} />
                      {msg.edited_at && <span className="message-edited"> (edited)</span>}
                    </div>
                  )}
                  {msg.link_preview && (
                    <LinkPreviewCard preview={msg.link_preview} onImageClick={setLightboxSrc} />
                  )}
                  {msg.reactions.length > 0 && (
                    <div className="message-reaction-pills">
                      {msg.reactions.map((r) => {
                        const mineReaction = !!user && r.user_ids.includes(user.id)
                        return (
                          <button
                            key={r.emoji}
                            type="button"
                            className={`message-reaction-pill${mineReaction ? ' message-reaction-pill-mine' : ''}`}
                            title={r.user_ids.map(displayNameForUserId).join(', ')}
                            onClick={() => onReact(msg.id, r.emoji)}
                          >
                            <span>{r.emoji}</span>
                            <span>{r.count}</span>
                          </button>
                        )
                      })}
                    </div>
                  )}
                </>
              )}
            </div>
            {!editing && !deleted && (
              <div className="message-row-actions">
                <div className="message-reaction-wrap">
                  <button
                    type="button"
                    className="message-reaction-trigger"
                    onClick={(e) => {
                      if (reactingId === msg.id) {
                        setReactingId(null)
                        return
                      }
                      // Flip upward when the picker wouldn't fit below the
                      // trigger -- a message near the bottom of the
                      // scrolled list otherwise opens a picker that runs
                      // off-screen and can't be used.
                      const rect = e.currentTarget.getBoundingClientRect()
                      const spaceBelow = window.innerHeight - rect.bottom
                      setReactionPlacement(spaceBelow < EMOJI_PICKER_MAX_HEIGHT ? 'above' : 'below')
                      setReactingId(msg.id)
                    }}
                    aria-label="Add reaction"
                  >
                    🙂
                  </button>
                  {reactingId === msg.id && (
                    <EmojiPicker
                      onPick={(emoji) => {
                        onReact(msg.id, emoji)
                        setReactingId(null)
                      }}
                      onClose={() => setReactingId(null)}
                      placement={reactionPlacement}
                      align="right"
                    />
                  )}
                </div>
                {mine && (
                  <button
                    type="button"
                    className="message-edit-link"
                    onClick={() => startEdit(msg)}
                    aria-label="Edit message"
                  >
                    Edit
                  </button>
                )}
                {mine && (
                  <button
                    type="button"
                    className="message-delete-link"
                    onClick={() => handleDelete(msg.id)}
                    aria-label="Delete message"
                  >
                    Delete
                  </button>
                )}
              </div>
            )}
          </div>
        )
      })}
      <div ref={bottomRef} />
      {lightboxSrc && <ImageLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />}
      {videoLightbox && (
        <VideoLightbox
          src={videoLightbox.src}
          filename={videoLightbox.filename}
          onClose={() => setVideoLightbox(null)}
        />
      )}
      {previewFile && (
        <FilePreviewModal
          roomId={roomId}
          file={previewFile}
          kind={getPreviewKind(previewFile.filename) ?? 'text'}
          onClose={() => setPreviewFile(null)}
        />
      )}
    </div>
  )
}

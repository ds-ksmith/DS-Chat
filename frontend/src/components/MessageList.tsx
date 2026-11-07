import type { CSSProperties, MouseEvent as ReactMouseEvent } from 'react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { getRoomFileUrl, getRoomImageUrl } from '../api/rooms'
import { useAuth } from '../context/AuthContext'
import { useLocalDay } from '../hooks/useLocalDay'
import { formatFileSize } from '../lib/fileSize'
import { formatMessageTime, formatMessageTimeTitle } from '../lib/formatMessageTime'
import { avatarUrlFor, displayNameFor, isGroupStart, senderColorIndex, statusFor } from '../lib/messageGrouping'
import type { ChatMessageEnvelope, Message, MessageFileInfo, RoomMember } from '../types'
import { EMOJI_PICKER_MAX_HEIGHT, EmojiPicker } from './EmojiPicker'
import { FilePreviewModal, getPreviewKind } from './FilePreviewModal'
import { ImageLightbox } from './ImageLightbox'
import { LinkPreviewCard } from './LinkPreviewCard'
import { EMOJI_SCALE_MULTIPLIER, EmojiGlyph, MessageContent } from './MessageContent'
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
  // Paging back through older history. All optional: a list that never
  // passes them just has no older page to offer.
  hasMoreOlder?: boolean
  loadingOlder?: boolean
  olderError?: string | null
  onLoadOlder?: () => void
  // Bumped each time the user sends a message, so the list can jump to the
  // bottom to show it even if they had scrolled back. (Not inferred from the
  // newest message being theirs: a history refresh briefly shows an older
  // message of theirs last, which would look the same.)
  scrollToBottomSignal?: number
}

// How close to the top (px) a scroll has to get before the next older page is
// requested -- early enough that it's usually there before the user arrives.
const LOAD_OLDER_THRESHOLD_PX = 300

export function MessageList({
  roomId,
  messages,
  members,
  myRooms,
  onEdit,
  onReact,
  onDelete,
  hasMoreOlder = false,
  loadingOlder = false,
  olderError = null,
  onLoadOlder,
  scrollToBottomSignal = 0,
}: MessageListProps) {
  const { user } = useAuth()
  const now = useLocalDay()
  // #71: same viewer preference MessageContent applies to in-text emoji,
  // looked up separately here since a reaction pill isn't a descendant of
  // that component's wrapper div (see EmojiGlyph's own comment).
  const emojiScale = EMOJI_SCALE_MULTIPLIER[user?.emoji_scale ?? 'normal']
  const containerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  // Whether the view should be pinned to the latest message -- true on
  // opening a room and whenever the user is at the bottom, flipped off as
  // soon as they scroll away from it. Read by the image-load handler below so a
  // late-loading image doesn't yank someone back down mid-scrollback.
  const pinnedToBottomRef = useRef(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
  const [videoLightbox, setVideoLightbox] = useState<{ src: string; filename: string } | null>(null)
  const [reactingId, setReactingId] = useState<string | null>(null)
  // #78: a message has two buttons that open the same picker (the hover-row
  // one and the one at the end of its reaction pills); this says which one
  // the picker belongs to, so it renders next to the button that was used.
  const [reactingFrom, setReactingFrom] = useState<'row' | 'pills'>('row')
  const [reactionPlacement, setReactionPlacement] = useState<'above' | 'below'>('below')
  const [previewFile, setPreviewFile] = useState<MessageFileInfo | null>(null)
  const memberUsernames = useMemo(() => new Set(members.map((m) => m.username)), [members])

  function displayNameForUserId(userId: string): string {
    const member = members.find((m) => m.user_id === userId)
    return member?.display_name || member?.username || 'someone'
  }

  function toggleReactionPicker(
    e: ReactMouseEvent<HTMLButtonElement>,
    messageId: string,
    from: 'row' | 'pills',
  ) {
    if (reactingId === messageId && reactingFrom === from) {
      setReactingId(null)
      return
    }
    // Flip upward when the picker wouldn't fit below the trigger -- a
    // message near the bottom of the scrolled list otherwise opens a
    // picker that runs off-screen and can't be used.
    const rect = e.currentTarget.getBoundingClientRect()
    const spaceBelow = window.innerHeight - rect.bottom
    setReactionPlacement(spaceBelow < EMOJI_PICKER_MAX_HEIGHT ? 'above' : 'below')
    setReactingFrom(from)
    setReactingId(messageId)
  }

  // Paging back. Asking for an older page records where the list was
  // scrolled to, so that once those messages are added above, the view can be
  // put back exactly where it was instead of jumping.
  const olderAnchorRef = useRef<{ height: number; top: number } | null>(null)
  const skipBottomScrollRef = useRef(false)
  const firstIdRef = useRef(messages[0]?.id)
  // Refs rather than closing over the props: the scroll listener below is
  // attached once and must always see the current values.
  const canLoadOlderRef = useRef(false)
  canLoadOlderRef.current = hasMoreOlder && !loadingOlder && !olderError && !!onLoadOlder
  const onLoadOlderRef = useRef(onLoadOlder)
  onLoadOlderRef.current = onLoadOlder

  function requestOlder() {
    const container = containerRef.current
    if (!container || !onLoadOlderRef.current) return
    olderAnchorRef.current = { height: container.scrollHeight, top: container.scrollTop }
    onLoadOlderRef.current()
  }

  // Runs before paint, so the correction is never visible as a flash. Only
  // acts when messages were added *above* the old first one while an anchor
  // is waiting -- an ordinary new message at the bottom leaves it alone.
  useLayoutEffect(() => {
    const container = containerRef.current
    const first = messages[0]?.id
    const anchor = olderAnchorRef.current
    if (container && anchor && first !== firstIdRef.current) {
      container.scrollTop = anchor.top + (container.scrollHeight - anchor.height)
      skipBottomScrollRef.current = true
    }
    firstIdRef.current = first
  }, [messages])

  // The request is over (loaded, empty, failed): nothing left to restore.
  // Declared after the effect above so a result that lands in the same render
  // as the end of loading is still restored first.
  useLayoutEffect(() => {
    if (!loadingOlder) olderAnchorRef.current = null
  }, [loadingOlder])

  const prevRoomIdRef = useRef<string | null>(null)
  useEffect(() => {
    if (skipBottomScrollRef.current) {
      // This change was older messages loading in above -- not something
      // to follow down to the bottom.
      skipBottomScrollRef.current = false
      return
    }
    const roomChanged = prevRoomIdRef.current !== roomId
    prevRoomIdRef.current = roomId
    // Follows new messages to the bottom when the user is already there or
    // on opening a room -- but not while they're scrolled back reading older
    // history, which would otherwise be yanked away by every incoming
    // message. (Sending one has its own signal, below.)
    if (roomChanged || pinnedToBottomRef.current) {
      pinnedToBottomRef.current = true
      bottomRef.current?.scrollIntoView({ block: 'end' })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deliberately keyed on length, not the array: it re-runs per new message, not per edit/reaction
  }, [roomId, messages.length])

  useEffect(() => {
    if (scrollToBottomSignal === 0) return
    pinnedToBottomRef.current = true
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [scrollToBottomSignal])

  // A list too short to scroll never fires a scroll event, so without this a
  // tall window showing a full page of short messages would have no way to
  // reach the older ones short of the button.
  useEffect(() => {
    const container = containerRef.current
    if (container && canLoadOlderRef.current && container.scrollHeight <= container.clientHeight) {
      requestOlder()
    }
  }, [messages, hasMoreOlder, loadingOlder, olderError])

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
      if (container.scrollTop < LOAD_OLDER_THRESHOLD_PX && canLoadOlderRef.current) requestOlder()
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
      {hasMoreOlder || loadingOlder || olderError ? (
        <div className="message-list-older">
          {loadingOlder ? (
            <span>Loading earlier messages…</span>
          ) : (
            <>
              {olderError && <span className="message-list-older-error">{olderError}</span>}
              <button type="button" onClick={requestOlder}>
                {olderError ? 'Try again' : 'Load earlier messages'}
              </button>
            </>
          )}
        </div>
      ) : (
        messages.length > 0 && <div className="message-list-start">Start of conversation</div>
      )}
      {messages.map((msg, i) => {
        const mine = msg.user_id === user?.id
        const prev = messages[i - 1]
        // Mattermost-style grouping: every message shows who sent it, but
        // consecutive messages from the same sender only repeat the
        // avatar/name/timestamp header on the first one in the run --
        // applies uniformly, including to your own messages. Also breaks on
        // a long gap or a new calendar day -- see isGroupStart.
        const groupStart = isGroupStart(prev, msg)
        const editing = editingId === msg.id
        const deleted = !!msg.deleted_at

        return (
          <div key={msg.id} className={`message-row${groupStart ? ' message-row-start' : ''}`}>
            <div className="message-avatar-slot">
              {groupStart && (
                <UserAvatar
                  username={msg.username}
                  colorIndex={senderColorIndex(msg.username, members)}
                  avatarUrl={avatarUrlFor(msg.username, members)}
                  status={statusFor(msg.username, members)}
                />
              )}
            </div>
            <div className="message-content">
              {groupStart && (
                <div className="message-header">
                  <span className="message-author">{displayNameFor(msg.username, members)}</span>
                  <span className="message-time" title={formatMessageTimeTitle(msg.created_at)}>
                    {formatMessageTime(msg.created_at, now)}
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
                            {/* No .inline-emoji here -- EmojiGlyph's own fallback branch
                                already applies it, and stacking it here too would double
                                the font-size multiplication for a custom-emoji img. */}
                            <span style={{ '--emoji-scale': emojiScale } as CSSProperties}>
                              <EmojiGlyph value={r.emoji} />
                            </span>
                            <span>{r.count}</span>
                          </button>
                        )
                      })}
                      <div className="message-reaction-add-wrap">
                        <button
                          type="button"
                          className="message-reaction-pill message-reaction-add"
                          onClick={(e) => toggleReactionPicker(e, msg.id, 'pills')}
                          aria-label="Add reaction"
                        >
                          <span aria-hidden="true">+</span>
                          <span aria-hidden="true">🙂</span>
                        </button>
                        {reactingId === msg.id && reactingFrom === 'pills' && (
                          <EmojiPicker
                            onPick={(emoji) => {
                              onReact(msg.id, emoji)
                              setReactingId(null)
                            }}
                            onClose={() => setReactingId(null)}
                            placement={reactionPlacement}
                            align="left"
                          />
                        )}
                      </div>
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
                    onClick={(e) => toggleReactionPicker(e, msg.id, 'row')}
                    aria-label="Add reaction"
                  >
                    🙂
                  </button>
                  {reactingId === msg.id && reactingFrom === 'row' && (
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

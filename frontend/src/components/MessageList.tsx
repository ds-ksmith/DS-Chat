import { useEffect, useRef, useState } from 'react'
import { getRoomImageUrl } from '../api/rooms'
import { useAuth } from '../context/AuthContext'
import { avatarUrlFor, displayNameFor, senderColorIndex } from '../lib/messageGrouping'
import type { ChatMessageEnvelope, Message, RoomMember } from '../types'
import { EmojiPicker } from './EmojiPicker'
import { ImageLightbox } from './ImageLightbox'
import { MessageContent } from './MessageContent'
import { UserAvatar } from './UserAvatar'
import './MessageList.css'

interface MessageListProps {
  roomId: string
  messages: (Message | ChatMessageEnvelope)[]
  members: RoomMember[]
  onEdit: (messageId: string, content: string) => void
  onReact: (messageId: string, emoji: string) => void
}

export function MessageList({ roomId, messages, members, onEdit, onReact }: MessageListProps) {
  const { user } = useAuth()
  const bottomRef = useRef<HTMLDivElement>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
  const [reactingId, setReactingId] = useState<string | null>(null)

  function displayNameForUserId(userId: string): string {
    const member = members.find((m) => m.user_id === userId)
    return member?.display_name || member?.username || 'someone'
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length])

  function startEdit(msg: Message | ChatMessageEnvelope) {
    setEditingId(msg.id)
    setDraft(msg.content ?? '')
  }

  function commitEdit(messageId: string) {
    const trimmed = draft.trim()
    if (trimmed) onEdit(messageId, trimmed)
    setEditingId(null)
  }

  return (
    <div className="message-list">
      {messages.map((msg, i) => {
        const mine = msg.user_id === user?.id
        const prev = messages[i - 1]
        // Mattermost-style grouping: every message shows who sent it, but
        // consecutive messages from the same sender only repeat the
        // avatar/name/timestamp header on the first one in the run --
        // applies uniformly, including to your own messages.
        const isGroupStart = !prev || prev.user_id !== msg.user_id
        const editing = editingId === msg.id

        return (
          <div key={msg.id} className={`message-row${isGroupStart ? ' message-row-start' : ''}`}>
            <div className="message-avatar-slot">
              {isGroupStart && (
                <UserAvatar
                  username={msg.username}
                  colorIndex={senderColorIndex(msg.username, members)}
                  avatarUrl={avatarUrlFor(msg.username, members)}
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
              {editing ? (
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
                  {msg.content && (
                    <div className="message-text">
                      <MessageContent content={msg.content} />
                      {msg.edited_at && <span className="message-edited"> (edited)</span>}
                    </div>
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
            {!editing && (
              <div className="message-row-actions">
                <div className="message-reaction-wrap">
                  <button
                    type="button"
                    className="message-reaction-trigger"
                    onClick={() => setReactingId(reactingId === msg.id ? null : msg.id)}
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
                      placement="below"
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
              </div>
            )}
          </div>
        )
      })}
      <div ref={bottomRef} />
      {lightboxSrc && <ImageLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />}
    </div>
  )
}

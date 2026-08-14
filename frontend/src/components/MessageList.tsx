import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { senderColorIndex } from '../lib/messageGrouping'
import type { ChatMessageEnvelope, Message, RoomMember } from '../types'
import { UserAvatar } from './UserAvatar'
import './MessageList.css'

interface MessageListProps {
  messages: (Message | ChatMessageEnvelope)[]
  members: RoomMember[]
  onEdit: (messageId: string, content: string) => void
}

export function MessageList({ messages, members, onEdit }: MessageListProps) {
  const { user } = useAuth()
  const bottomRef = useRef<HTMLDivElement>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length])

  function startEdit(msg: Message | ChatMessageEnvelope) {
    setEditingId(msg.id)
    setDraft(msg.content)
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
        const showAvatar = !mine && (!prev || prev.user_id !== msg.user_id)
        const showName = showAvatar
        const editing = editingId === msg.id

        return (
          <div key={msg.id} className={`message-row${mine ? ' message-row-mine' : ''}`}>
            {!mine && (
              <div className="message-avatar-slot">
                {showAvatar && (
                  <UserAvatar username={msg.username} colorIndex={senderColorIndex(msg.username, members)} />
                )}
              </div>
            )}
            <div className="message-bubble-wrap">
              {showName && <div className="message-author">{msg.username}</div>}
              {editing ? (
                <input
                  autoFocus
                  className="message-edit-input"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitEdit(msg.id)
                    if (e.key === 'Escape') setEditingId(null)
                  }}
                  onBlur={() => commitEdit(msg.id)}
                />
              ) : (
                <div className={`message-bubble${mine ? ' message-bubble-mine' : ''}`}>
                  {msg.content}
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
              <div className="message-time">
                {new Date(msg.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                {msg.edited_at && <span className="message-edited"> (edited)</span>}
              </div>
            </div>
          </div>
        )
      })}
      <div ref={bottomRef} />
    </div>
  )
}

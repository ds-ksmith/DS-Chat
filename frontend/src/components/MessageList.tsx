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
                <UserAvatar username={msg.username} colorIndex={senderColorIndex(msg.username, members)} />
              )}
            </div>
            <div className="message-content">
              {isGroupStart && (
                <div className="message-header">
                  <span className="message-author">{msg.username}</span>
                  <span className="message-time">
                    {new Date(msg.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                  </span>
                </div>
              )}
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
                <div className="message-text">
                  {msg.content}
                  {msg.edited_at && <span className="message-edited"> (edited)</span>}
                </div>
              )}
            </div>
            {mine && !editing && (
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
        )
      })}
      <div ref={bottomRef} />
    </div>
  )
}

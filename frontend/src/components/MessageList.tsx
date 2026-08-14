import { useEffect, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { senderColorIndex } from '../lib/messageGrouping'
import type { ChatMessageEnvelope, Message, RoomMember } from '../types'
import { UserAvatar } from './UserAvatar'
import './MessageList.css'

interface MessageListProps {
  messages: (Message | ChatMessageEnvelope)[]
  members: RoomMember[]
}

export function MessageList({ messages, members }: MessageListProps) {
  const { user } = useAuth()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length])

  return (
    <div className="message-list">
      {messages.map((msg, i) => {
        const mine = msg.user_id === user?.id
        const prev = messages[i - 1]
        const showAvatar = !mine && (!prev || prev.user_id !== msg.user_id)
        const showName = showAvatar

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
              <div className={`message-bubble${mine ? ' message-bubble-mine' : ''}`}>{msg.content}</div>
              <div className="message-time">
                {new Date(msg.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
              </div>
            </div>
          </div>
        )
      })}
      <div ref={bottomRef} />
    </div>
  )
}

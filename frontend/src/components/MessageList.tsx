import { useEffect, useRef } from 'react'
import type { ChatMessageEnvelope, Message } from '../types'

interface DisplayMessage {
  id: string
  username: string
  content: string
  created_at: string
}

interface MessageListProps {
  messages: (Message | ChatMessageEnvelope)[]
  usernames: Record<string, string>
}

export function MessageList({ messages, usernames }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length])

  const display: DisplayMessage[] = messages.map((m) => ({
    id: m.id,
    content: m.content,
    created_at: m.created_at,
    username: 'username' in m ? m.username : usernames[m.user_id] ?? m.user_id,
  }))

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem' }}>
      {display.map((m) => (
        <div key={m.id} style={{ marginBottom: '0.5rem' }}>
          <strong>{m.username}</strong>{' '}
          <span style={{ color: '#888', fontSize: '0.8em' }}>
            {new Date(m.created_at).toLocaleTimeString()}
          </span>
          <div>{m.content}</div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

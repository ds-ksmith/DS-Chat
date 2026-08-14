import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getRoomMessages } from '../api/rooms'
import { MessageInput } from '../components/MessageInput'
import { MessageList } from '../components/MessageList'
import { useAuth } from '../context/AuthContext'
import { useChatSocket } from '../ws/useChatSocket'
import type { ChatMessageEnvelope, Message, ServerEnvelope } from '../types'

export function ChatRoomPage() {
  const { roomId } = useParams<{ roomId: string }>()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [history, setHistory] = useState<Message[]>([])
  const [live, setLive] = useState<ChatMessageEnvelope[]>([])
  const [wsError, setWsError] = useState<string | null>(null)

  useEffect(() => {
    if (!roomId) return
    setHistory([])
    setLive([])
    getRoomMessages(roomId).then(setHistory).catch((err) => setWsError(String(err)))
  }, [roomId])

  const onMessage = useCallback((envelope: ServerEnvelope) => {
    if (envelope.type === 'message') {
      setLive((prev) => [...prev, envelope])
    } else if (envelope.type === 'error') {
      setWsError(envelope.detail)
    }
  }, [])

  const onUnauthenticated = useCallback(() => navigate('/login'), [navigate])

  const { connected, send } = useChatSocket({
    roomId: roomId ?? '',
    onMessage,
    onUnauthenticated,
  })

  if (!roomId) return null

  const usernames = user ? { [user.id]: user.username } : {}

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', maxWidth: 640, margin: '0 auto' }}>
      <header style={{ padding: '0.5rem', borderBottom: '1px solid #ddd' }}>
        <button onClick={() => navigate('/rooms')}>&larr; Rooms</button>
        {!connected && <span style={{ marginLeft: '1rem', color: '#888' }}>Connecting...</span>}
      </header>

      {wsError && <p style={{ color: 'red', padding: '0 0.5rem' }}>{wsError}</p>}

      <MessageList messages={[...history, ...live]} usernames={usernames} />
      <MessageInput disabled={!connected} onSend={send} />
    </div>
  )
}

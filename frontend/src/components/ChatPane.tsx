import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getRoomMessages } from '../api/rooms'
import { useChatSocket } from '../ws/useChatSocket'
import type { ChatMessageEnvelope, Message, MyRoomItem, RoomMember, ServerEnvelope } from '../types'
import { Composer } from './Composer'
import { MessageList } from './MessageList'
import './ChatPane.css'

interface ChatPaneProps {
  room: MyRoomItem
  members: RoomMember[]
  isMobile: boolean
  onBack: () => void
  onToggleInfo: () => void
  infoOpen: boolean
}

export function ChatPane({ room, members, isMobile, onBack, onToggleInfo, infoOpen }: ChatPaneProps) {
  const navigate = useNavigate()
  const [history, setHistory] = useState<Message[]>([])
  const [live, setLive] = useState<ChatMessageEnvelope[]>([])
  const [wsError, setWsError] = useState<string | null>(null)

  useEffect(() => {
    setHistory([])
    setLive([])
    setWsError(null)
    getRoomMessages(room.id).then(setHistory).catch((err) => setWsError(String(err)))
  }, [room.id])

  const onMessage = useCallback((envelope: ServerEnvelope) => {
    if (envelope.type === 'message') {
      setLive((prev) => [...prev, envelope])
    } else if (envelope.type === 'error') {
      setWsError(envelope.detail)
    }
  }, [])

  const onUnauthenticated = useCallback(() => navigate('/login'), [navigate])

  const { connected, send } = useChatSocket({ roomId: room.id, onMessage, onUnauthenticated })

  return (
    <section className="chat-pane">
      <header className="chat-pane-header">
        {isMobile && (
          <button type="button" className="chat-pane-back" onClick={onBack} aria-label="Back to rooms">
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <polyline points="14,4 6,10 14,16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
        <div className="chat-pane-title-block">
          <div className="chat-pane-title">#{room.name}</div>
          <div className="chat-pane-subtitle">{members.length} member{members.length === 1 ? '' : 's'}</div>
        </div>
        <button
          type="button"
          className={`chat-pane-info-btn${infoOpen ? ' chat-pane-info-btn-active' : ''}`}
          onClick={onToggleInfo}
          aria-label="Room details"
          aria-pressed={infoOpen}
        >
          <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
            <circle cx="10" cy="6.4" r="1" fill="currentColor" />
            <rect x="9" y="9" width="2" height="6" rx="1" fill="currentColor" />
          </svg>
        </button>
      </header>

      {wsError && <p className="chat-pane-error">{wsError}</p>}

      <MessageList messages={[...history, ...live]} members={members} />
      <Composer roomName={room.name} disabled={!connected} onSend={send} />
    </section>
  )
}

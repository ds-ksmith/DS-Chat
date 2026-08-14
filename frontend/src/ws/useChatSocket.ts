import { useCallback, useEffect, useRef, useState } from 'react'
import type { ServerEnvelope } from '../types'

interface UseChatSocketOptions {
  roomId: string
  onMessage: (envelope: ServerEnvelope) => void
  onUnauthenticated: () => void
}

export function useChatSocket({ roomId, onMessage, onUnauthenticated }: UseChatSocketOptions) {
  const socketRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage
  const onUnauthenticatedRef = useRef(onUnauthenticated)
  onUnauthenticatedRef.current = onUnauthenticated

  useEffect(() => {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${location.host}/ws/chat`)
    socketRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      ws.send(JSON.stringify({ type: 'join', room_id: roomId }))
    }

    ws.onmessage = (event) => {
      onMessageRef.current(JSON.parse(event.data) as ServerEnvelope)
    }

    ws.onclose = (event) => {
      setConnected(false)
      if (event.code === 4401) {
        onUnauthenticatedRef.current()
      }
    }

    return () => {
      ws.close()
      socketRef.current = null
    }
  }, [roomId])

  const send = useCallback((content: string) => {
    const ws = socketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'message', room_id: roomId, content }))
  }, [roomId])

  const sendEdit = useCallback((messageId: string, content: string) => {
    const ws = socketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'edit', room_id: roomId, message_id: messageId, content }))
  }, [roomId])

  return { connected, send, sendEdit }
}

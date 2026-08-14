import { useCallback, useEffect, useRef, useState } from 'react'
import type { ServerEnvelope } from '../types'

interface UseChatSocketOptions {
  roomId: string
  onMessage: (envelope: ServerEnvelope) => void
  onUnauthenticated: () => void
}

const RECONNECT_BASE_DELAY_MS = 1000
const RECONNECT_MAX_DELAY_MS = 30000

export function useChatSocket({ roomId, onMessage, onUnauthenticated }: UseChatSocketOptions) {
  const socketRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage
  const onUnauthenticatedRef = useRef(onUnauthenticated)
  onUnauthenticatedRef.current = onUnauthenticated

  useEffect(() => {
    let stopped = false
    let reconnectDelay = RECONNECT_BASE_DELAY_MS
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    function connect() {
      const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${protocol}://${location.host}/ws/chat`)
      socketRef.current = ws

      ws.onopen = () => {
        // Guards against React StrictMode's dev-only double-invoke of this
        // effect (mount -> cleanup -> mount again): the first socket gets
        // abandoned in cleanup, but its own open/close events can still
        // fire asynchronously afterward. Without this check, a stale
        // socket's callbacks can stomp on state that the second (real)
        // socket already owns.
        if (socketRef.current !== ws) return
        reconnectDelay = RECONNECT_BASE_DELAY_MS
        setConnected(true)
        ws.send(JSON.stringify({ type: 'join', room_id: roomId }))
      }

      ws.onmessage = (event) => {
        if (socketRef.current !== ws) return
        onMessageRef.current(JSON.parse(event.data) as ServerEnvelope)
      }

      ws.onclose = (event) => {
        // Same guard as onopen -- a stale/abandoned socket's close event
        // must not null out the reference to whatever socket has actually
        // taken over since (this was a real bug: the abandoned socket's
        // delayed onclose was silently orphaning a perfectly live
        // connection, with nothing left referencing it to send on).
        if (socketRef.current !== ws) return
        setConnected(false)
        socketRef.current = null

        if (event.code === 4401) {
          onUnauthenticatedRef.current()
          return
        }
        if (stopped) return

        // Unexpected close -- a deploy restarting the app server, a brief
        // network blip, or (absent any app-level ping/pong) an idle
        // connection getting recycled by a reverse proxy in front of it.
        // Retry with exponential backoff instead of leaving the chat
        // silently dead until the user manually reloads.
        reconnectTimer = setTimeout(connect, reconnectDelay)
        reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_DELAY_MS)
      }
    }

    connect()

    return () => {
      stopped = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [roomId])

  const send = useCallback((content: string, imageId?: string) => {
    const ws = socketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(
      JSON.stringify({ type: 'message', room_id: roomId, content: content || null, image_id: imageId ?? null }),
    )
  }, [roomId])

  const sendEdit = useCallback((messageId: string, content: string) => {
    const ws = socketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'edit', room_id: roomId, message_id: messageId, content }))
  }, [roomId])

  return { connected, send, sendEdit }
}

import { useCallback, useEffect, useRef, useState } from 'react'
import { isDesktopNotificationsSupported } from '../lib/desktopBridge'
import { checkForUpdate } from '../lib/swUpdate'
import type { ServerEnvelope } from '../types'

interface UseChatSocketOptions {
  onUnauthenticated: () => void
}

const RECONNECT_BASE_DELAY_MS = 1000
const RECONNECT_MAX_DELAY_MS = 30000

// #49 follow-up: a bare `document.visibilityState` check (below) means "not
// minimized/hidden" -- in a browser tab that's a decent proxy for "the user
// could be looking at this," since visibility already tracks whether this is
// the active tab. Inside an Electron BrowserWindow it isn't: visibilityState
// only flips on minimize/hide, not on losing OS focus, so a window sitting
// open-but-unfocused behind another app never registers as "gone." That's
// exactly the state a desktop notification needs to fire in, so desktop mode
// additionally requires document.hasFocus(). Gated on desktopMode so regular
// browser-tab behavior (already relied on by Web Push and the unread dot) is
// completely unchanged.
const desktopMode = isDesktopNotificationsSupported()

function isPresent(): boolean {
  return document.visibilityState === 'visible' && (!desktopMode || document.hasFocus())
}

// One connection per authenticated session, established as soon as the app
// shell mounts -- not per-room. A room is just something this socket can be
// told to "join"/"leave" while it's open; the connection itself persists
// across room switches and while no room is open at all, since a per-user
// signal (e.g. "you were added to a room") has to reach the client whether
// or not any room is currently open.
export function useChatSocket({ onUnauthenticated }: UseChatSocketOptions) {
  const socketRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const onUnauthenticatedRef = useRef(onUnauthenticated)
  onUnauthenticatedRef.current = onUnauthenticated
  const subscribersRef = useRef(new Set<(envelope: ServerEnvelope) => void>())
  // Rooms the app *wants* joined (set via joinRoom/leaveRoom) -- distinct
  // from whether the server currently has this connection joined, which is
  // additionally gated on document visibility below. A backgrounded tab
  // stays technically connected but tells the server "leave" for every
  // desired room, so the server's existing offline-push logic (which keys
  // off room presence, not raw connection state) correctly treats a
  // backgrounded user the same as a disconnected one instead of assuming a
  // live WebSocket delivery the user can't actually see will do the job.
  const desiredRoomsRef = useRef(new Set<string>())
  const isVisibleRef = useRef(isPresent())

  const sendRoomFrame = useCallback((type: 'join' | 'leave', roomId: string) => {
    const ws = socketRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, room_id: roomId }))
    }
  }, [])

  useEffect(() => {
    let stopped = false
    let reconnectDelay = RECONNECT_BASE_DELAY_MS
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    // False only for the very first connect() of this effect's lifetime --
    // every connect() after that was triggered by onclose's retry logic,
    // i.e. this is a genuine reconnect. A reconnect reliably means the
    // backend process just restarted (a deploy kills every open WS), so
    // it's used as the trigger for an out-of-band SW update check instead
    // of waiting on UpdateBanner's hourly poll -- see lib/swUpdate.ts.
    let hasConnectedBefore = false

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
        if (hasConnectedBefore) checkForUpdate()
        hasConnectedBefore = true
        reconnectDelay = RECONNECT_BASE_DELAY_MS
        setConnected(true)
        // Re-join whatever rooms were joined before a reconnect -- the
        // server has no memory of a dropped connection's prior state. Only
        // while visible (checked live, not from the ref -- see joinRoom's
        // comment): reconnecting from a backgrounded tab should stay
        // "left" for the same reason backgrounding leaves in the first
        // place (see desiredRoomsRef's comment above).
        isVisibleRef.current = isPresent()
        if (isVisibleRef.current) {
          for (const roomId of desiredRoomsRef.current) {
            sendRoomFrame('join', roomId)
          }
        }
      }

      ws.onmessage = (event) => {
        if (socketRef.current !== ws) return
        const envelope = JSON.parse(event.data) as ServerEnvelope
        for (const handler of subscribersRef.current) handler(envelope)
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
  }, [sendRoomFrame])

  useEffect(() => {
    function handlePresenceChange() {
      const present = isPresent()
      if (present === isVisibleRef.current) return
      isVisibleRef.current = present
      for (const roomId of desiredRoomsRef.current) {
        sendRoomFrame(present ? 'join' : 'leave', roomId)
      }
    }
    document.addEventListener('visibilitychange', handlePresenceChange)
    // Only in desktop mode -- see isPresent()'s comment above. Blur/focus on
    // a browser tab fire on every click into/out of the page (e.g. opening
    // devtools), which would be a far noisier signal than intended there;
    // browser tabs stay on visibilitychange alone, unchanged from before.
    if (desktopMode) {
      window.addEventListener('focus', handlePresenceChange)
      window.addEventListener('blur', handlePresenceChange)
    }
    return () => {
      document.removeEventListener('visibilitychange', handlePresenceChange)
      if (desktopMode) {
        window.removeEventListener('focus', handlePresenceChange)
        window.removeEventListener('blur', handlePresenceChange)
      }
    }
  }, [sendRoomFrame])

  const subscribe = useCallback((handler: (envelope: ServerEnvelope) => void) => {
    subscribersRef.current.add(handler)
    return () => {
      subscribersRef.current.delete(handler)
    }
  }, [])

  const joinRoom = useCallback(
    (roomId: string) => {
      desiredRoomsRef.current.add(roomId)
      // Reads the live API, not a cached ref: a room can "mount" (calling
      // this) without genuine user interaction -- mobile Chrome can
      // silently discard and later reload a long-backgrounded tab from
      // memory, which re-runs this exact effect with nobody looking at the
      // screen. An earlier version of this trusted isVisibleRef and/or
      // sent unconditionally on the theory that "you can't click into a
      // room while hidden" -- true for a real click, not true for a silent
      // background reload, which re-joined the room's presence on every
      // such reload with no matching "leave" (the discard skips normal
      // unmount cleanup), permanently suppressing push notifications for
      // that room until the tab was genuinely reopened. Checking fresh
      // here means a still-hidden reload correctly stays "left" -- the
      // room stays in desiredRoomsRef regardless, so the next genuine
      // foreground transition (handleVisibilityChange below) still joins
      // it, just deferred instead of wrongly immediate.
      isVisibleRef.current = isPresent()
      if (isVisibleRef.current) sendRoomFrame('join', roomId)
    },
    [sendRoomFrame],
  )

  const leaveRoom = useCallback(
    (roomId: string) => {
      desiredRoomsRef.current.delete(roomId)
      sendRoomFrame('leave', roomId)
    },
    [sendRoomFrame],
  )

  const send = useCallback((roomId: string, content: string, imageId?: string, fileId?: string) => {
    const ws = socketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(
      JSON.stringify({
        type: 'message',
        room_id: roomId,
        content: content || null,
        image_id: imageId ?? null,
        file_id: fileId ?? null,
      }),
    )
  }, [])

  const sendEdit = useCallback((roomId: string, messageId: string, content: string) => {
    const ws = socketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'edit', room_id: roomId, message_id: messageId, content }))
  }, [])

  const sendReaction = useCallback((roomId: string, messageId: string, emoji: string) => {
    const ws = socketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'reaction', room_id: roomId, message_id: messageId, emoji }))
  }, [])

  return { connected, subscribe, joinRoom, leaveRoom, send, sendEdit, sendReaction }
}

export type ChatSocketHandle = ReturnType<typeof useChatSocket>

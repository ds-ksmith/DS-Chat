import { useCallback, useEffect, useRef, useState } from 'react'
import { isDesktopNotificationsSupported } from '../lib/desktopBridge'
import { checkForUpdate } from '../lib/swUpdate'
import type { ServerEnvelope } from '../types'

interface UseChatSocketOptions {
  onUnauthenticated: () => void
}

const RECONNECT_BASE_DELAY_MS = 1000
const RECONNECT_MAX_DELAY_MS = 30000

// #76: the backend pings every 30s (WS_PING_INTERVAL_SECONDS in chat.py) --
// this needs to comfortably tolerate one missed ping plus ordinary network
// jitter before declaring the connection dead, not fire on the very first
// late beat.
const ZOMBIE_TIMEOUT_MS = 65000
const ZOMBIE_CHECK_INTERVAL_MS = 10000

const desktopMode = isDesktopNotificationsSupported()

// Room join/leave (live message delivery) depends only on visibility --
// "not minimized/hidden" -- exactly like a browser tab, in every mode.
//
// #49 originally had desktop mode additionally require document.hasFocus()
// here, on the theory that losing OS focus should count as "not present"
// the same way backgrounding a browser tab does. #59: that conflated two
// separate concerns onto one signal -- losing focus made the desktop client
// send "leave" for every open room, which stopped *live delivery* to a room
// still fully visible on screen, not just notification eligibility. A
// message wouldn't appear until the room was manually left and rejoined
// (e.g. switching rooms and back), which is what actually got reported.
// Focus now drives its own separate signal (see the "focus" WS frame below
// and FocusPresence server-side) instead of gating room membership at all.
function isVisible(): boolean {
  return document.visibilityState === 'visible'
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
  const isVisibleRef = useRef(isVisible())
  // #76: last time *anything* arrived on the socket (a real message, a
  // "ping", doesn't matter which) -- the only signal that a connection
  // sitting at readyState OPEN is actually still alive rather than a
  // zombie. Without this, a connection that dies without ever sending a
  // close frame (laptop sleep, a NAT silently dropping an idle mapping)
  // looks identical to a healthy-but-quiet one: onclose never fires, so the
  // already-correct reconnect+rejoin logic below never runs, and new
  // messages just stop arriving until something unrelated (e.g. switching
  // rooms, which refetches history over plain REST) papers over it.
  const lastActivityRef = useRef(Date.now())

  const sendRoomFrame = useCallback((type: 'join' | 'leave', roomId: string) => {
    const ws = socketRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, room_id: roomId }))
    }
  }, [])

  // #59: reports this desktop window's focus state as its own signal,
  // completely separate from room join/leave above -- see FocusPresence
  // server-side. No-op (and never called) outside desktop mode, matching
  // how the server only ever expects "focus" frames from the desktop
  // client at all.
  const sendFocusFrame = useCallback(() => {
    const ws = socketRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'focus', focused: document.hasFocus() }))
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
        lastActivityRef.current = Date.now()
        setConnected(true)
        // Re-join whatever rooms were joined before a reconnect -- the
        // server has no memory of a dropped connection's prior state. Only
        // while visible (checked live, not from the ref -- see joinRoom's
        // comment): reconnecting from a backgrounded tab should stay
        // "left" for the same reason backgrounding leaves in the first
        // place (see desiredRoomsRef's comment above).
        isVisibleRef.current = isVisible()
        if (isVisibleRef.current) {
          for (const roomId of desiredRoomsRef.current) {
            sendRoomFrame('join', roomId)
          }
        }
        // The server's FocusPresence state for this user doesn't survive a
        // dropped connection either (see chat.py's disconnect cleanup) --
        // report the current value fresh on every (re)connect, not just on
        // the next focus/blur transition, so a reconnect while unfocused
        // (e.g. after a deploy) doesn't leave the server assuming focused.
        if (desktopMode) sendFocusFrame()
      }

      ws.onmessage = (event) => {
        if (socketRef.current !== ws) return
        lastActivityRef.current = Date.now()
        const parsed = JSON.parse(event.data)
        // #76: the server's heartbeat -- purely transport-level, not a
        // domain event, so it's answered and swallowed right here instead
        // of being forwarded to subscribers (ServerEnvelope's own type
        // doesn't include it for exactly that reason).
        if (parsed.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }))
          return
        }
        const envelope = parsed as ServerEnvelope
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
        // network blip, or an idle connection getting recycled by a reverse
        // proxy in front of it. Retry with exponential backoff instead of
        // leaving the chat silently dead until the user manually reloads.
        reconnectTimer = setTimeout(connect, reconnectDelay)
        reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_DELAY_MS)
      }
    }

    connect()

    // #76: catches the case onclose can't -- a connection that dies without
    // ever sending a close frame at all (readyState stays OPEN forever) is
    // otherwise invisible to this hook. Forcing a close here just routes it
    // through the exact same onclose/reconnect/rejoin path as a normal
    // disconnect, rather than needing separate recovery logic of its own.
    const zombieCheckTimer = setInterval(() => {
      if (Date.now() - lastActivityRef.current > ZOMBIE_TIMEOUT_MS) {
        socketRef.current?.close()
      }
    }, ZOMBIE_CHECK_INTERVAL_MS)

    return () => {
      stopped = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      clearInterval(zombieCheckTimer)
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [sendRoomFrame, sendFocusFrame])

  useEffect(() => {
    function handleVisibilityChange() {
      const visible = isVisible()
      if (visible === isVisibleRef.current) return
      isVisibleRef.current = visible
      for (const roomId of desiredRoomsRef.current) {
        sendRoomFrame(visible ? 'join' : 'leave', roomId)
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [sendRoomFrame])

  // #59: focus/blur reporting, entirely separate from the visibility effect
  // above -- losing OS focus no longer touches room membership at all, just
  // this signal (consumed server-side by FocusPresence to widen desktop-
  // notification eligibility). Only in desktop mode: on a browser tab,
  // focus/blur fire on every click into/out of the page (e.g. opening
  // devtools), a far noisier signal than intended, and browser tabs don't
  // need it anyway -- visibility alone already matches pre-#49 behavior
  // there.
  useEffect(() => {
    if (!desktopMode) return
    window.addEventListener('focus', sendFocusFrame)
    window.addEventListener('blur', sendFocusFrame)
    return () => {
      window.removeEventListener('focus', sendFocusFrame)
      window.removeEventListener('blur', sendFocusFrame)
    }
  }, [sendFocusFrame])

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
      isVisibleRef.current = isVisible()
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

  const sendDelete = useCallback((roomId: string, messageId: string) => {
    const ws = socketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'delete', room_id: roomId, message_id: messageId }))
  }, [])

  return { connected, subscribe, joinRoom, leaveRoom, send, sendEdit, sendReaction, sendDelete }
}

export type ChatSocketHandle = ReturnType<typeof useChatSocket>

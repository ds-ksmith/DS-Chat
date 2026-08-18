import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useChatSocketContext } from '../context/ChatSocketContext'
import {
  getDesktopNotificationsEnabled,
  isDesktopNotificationsSupported,
  onDesktopNotificationClick,
  showDesktopNotification,
} from '../lib/desktopBridge'
import type { ServerEnvelope } from '../types'

// #49: renders nothing -- purely wires the authenticated socket's
// "desktop_notification" envelopes (see backend/app/services/
// message_events.py's _notify_offline_members) into DS Chat Desktop's
// native notification bridge, when running inside it. A no-op everywhere
// else (isDesktopNotificationsSupported() is false in every real browser).
//
// Mounted once, as a sibling of the routed pages inside ChatSocketProvider
// (App.tsx) -- that provider is already keyed by user.id and untouched by
// route changes, so this subscribes exactly once per authenticated session
// rather than accumulating a listener per navigation.
export function DesktopNotificationBridge() {
  const socket = useChatSocketContext()
  const navigate = useNavigate()

  useEffect(() => {
    return socket.subscribe((envelope: ServerEnvelope) => {
      if (envelope.type !== 'desktop_notification') return
      if (!isDesktopNotificationsSupported() || !getDesktopNotificationsEnabled()) return
      showDesktopNotification({
        eventId: envelope.id,
        roomId: envelope.room_id,
        title: envelope.title,
        body: envelope.body,
      })
    })
  }, [socket])

  useEffect(() => {
    const unsubscribe = onDesktopNotificationClick((roomId) => {
      // Always an internal room id from our own server, never a URL --
      // constructing the route here (not accepting a URL from the bridge)
      // is the point, not an implementation detail.
      navigate(`/rooms/${roomId}`)
    })
    return unsubscribe
  }, [navigate])

  return null
}

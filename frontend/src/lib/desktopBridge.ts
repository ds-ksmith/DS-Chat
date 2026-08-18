// #49: the native bridge DS Chat Desktop (a separate Electron wrapper, not
// this repo) exposes through a context-isolated preload script. Optional on
// `Window` -- absent entirely in every browser, and even inside the Electron
// shell a given method may be missing if the wrapper is an older build (see
// isDesktopNotificationsSupported/isDesktopClickListenerSupported below,
// each independently feature-tested rather than assumed present together).
export interface DesktopNotificationRequest {
  eventId: string
  roomId: string
  title: string
  body: string
}

declare global {
  interface Window {
    dsDesktop?: {
      setUnreadCount?(unreadRoomCount: number): void
      showNotification?(notification: DesktopNotificationRequest): void
      onNotificationClick?(callback: (roomId: string) => void): () => void
    }
  }
}

// Field limits Electron enforces on its side (documented in #49) -- applied
// here too, defensively, right at the bridge boundary rather than upstream
// in the shared notification-payload construction (server-side and Web
// Push have no such constraint; this is specifically the desktop bridge's
// contract, not a general notification-payload rule).
const MAX_TITLE_LENGTH = 100
const MAX_BODY_LENGTH = 500
const MAX_ID_LENGTH = 128

export function isDesktopNotificationsSupported(): boolean {
  return typeof window.dsDesktop?.showNotification === 'function'
}

export function isDesktopClickListenerSupported(): boolean {
  return typeof window.dsDesktop?.onNotificationClick === 'function'
}

// No-ops silently if the bridge or this specific method isn't present --
// callers don't need to guard, matching the rest of this module's
// capability-detect-per-method philosophy (see #49's "feature-test each
// bridge method before calling it").
export function showDesktopNotification(request: DesktopNotificationRequest): void {
  const show = window.dsDesktop?.showNotification
  if (!show) return
  show({
    eventId: request.eventId.slice(0, MAX_ID_LENGTH),
    roomId: request.roomId.slice(0, MAX_ID_LENGTH),
    title: request.title.slice(0, MAX_TITLE_LENGTH),
    body: request.body.slice(0, MAX_BODY_LENGTH),
  })
}

// Returns an unsubscribe function, or undefined if the bridge doesn't
// support click callbacks at all (older wrapper, or no bridge) -- callers
// should treat a missing return the same as a no-op cleanup.
export function onDesktopNotificationClick(callback: (roomId: string) => void): (() => void) | undefined {
  return window.dsDesktop?.onNotificationClick?.(callback)
}

const PREFERENCE_KEY = 'ds-chat-desktop-notifications-enabled'

// Purely local -- unlike Web Push, desktop notifications need no server
// round trip to enable/disable (no subscription row to create/delete), so
// this is a plain localStorage flag, deliberately decoupled from
// PushSubscription existence rather than reusing/repurposing it. Defaults
// to enabled: once running inside the desktop app at all, off-by-default
// would just mean the common case needs an extra click for no real benefit.
export function getDesktopNotificationsEnabled(): boolean {
  return localStorage.getItem(PREFERENCE_KEY) !== 'false'
}

export function setDesktopNotificationsEnabled(enabled: boolean): void {
  localStorage.setItem(PREFERENCE_KEY, String(enabled))
}

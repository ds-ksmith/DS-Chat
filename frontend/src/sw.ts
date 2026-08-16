/// <reference lib="webworker" />
import { CacheableResponsePlugin } from 'workbox-cacheable-response'
import { ExpirationPlugin } from 'workbox-expiration'
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { NetworkFirst, NetworkOnly } from 'workbox-strategies'

declare let self: ServiceWorkerGlobalScope

// registerType 'prompt' (vite.config.ts) means a newly-installed SW waits
// in the "waiting" state, still fully cached and ready, rather than
// unconditionally taking over -- it only activates once the page explicitly
// asks (UpdateBanner.tsx's updateServiceWorker(), which posts this message)
// after the user chooses to reload. Without this listener, skipWaiting()
// would need to run unconditionally at install time, defeating the point
// of asking first.
self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting()
  }
})
cleanupOutdatedCaches()

// The app shell -- same effect generateSW gave us automatically in Phase 3.
precacheAndRoute(self.__WB_MANIFEST)
registerRoute(
  new NavigationRoute(createHandlerBoundToURL('index.html'), {
    denylist: [/^\/api/, /^\/ws/],
  }),
)

const READ_CACHE_EXPIRATION = { maxEntries: 50, maxAgeSeconds: 7 * 24 * 60 * 60 }
const cacheableResponse = new CacheableResponsePlugin({ statuses: [0, 200] })
// Always prefer a live network response over the cache -- these routes back
// an actively-updating chat, so "stale" isn't an acceptable default the way
// it can be for e.g. static assets. StaleWhileRevalidate was tried here
// first, but it serves the *previous* cached response immediately and only
// refreshes the cache in the background for next time, which means every
// repeat visit shows content that's one visit behind until a manual reload
// (confirmed as the cause of #37 -- messages/rooms/members looking stale
// after leaving and returning to a room, or after another device's update).
// NetworkFirst keeps the same "readable while offline" behavior (falls back
// to cache only when the network request itself fails or times out) without
// that staleness while online.
const NETWORK_TIMEOUT_SECONDS = 4

// Ported from Phase 3's vite.config.ts `workbox.runtimeCaching` -- that
// option only applies to the generateSW strategy, so with a hand-written
// service worker (required below for the push/notificationclick handlers)
// these routes have to be registered explicitly instead.
registerRoute(({ url }) => url.pathname.startsWith('/api/auth/'), new NetworkOnly())

registerRoute(
  ({ url }) => url.pathname === '/api/rooms/mine',
  new NetworkFirst({
    cacheName: 'api-rooms-mine',
    networkTimeoutSeconds: NETWORK_TIMEOUT_SECONDS,
    plugins: [cacheableResponse, new ExpirationPlugin(READ_CACHE_EXPIRATION)],
  }),
)
registerRoute(
  ({ url }) => url.pathname === '/api/rooms',
  new NetworkFirst({
    cacheName: 'api-rooms-open',
    networkTimeoutSeconds: NETWORK_TIMEOUT_SECONDS,
    plugins: [cacheableResponse, new ExpirationPlugin(READ_CACHE_EXPIRATION)],
  }),
)
registerRoute(
  ({ url }) => /^\/api\/rooms\/[^/]+\/messages$/.test(url.pathname),
  new NetworkFirst({
    cacheName: 'api-room-messages',
    networkTimeoutSeconds: NETWORK_TIMEOUT_SECONDS,
    plugins: [cacheableResponse, new ExpirationPlugin(READ_CACHE_EXPIRATION)],
  }),
)
registerRoute(
  ({ url }) => /^\/api\/rooms\/[^/]+\/members$/.test(url.pathname),
  new NetworkFirst({
    cacheName: 'api-room-members',
    networkTimeoutSeconds: NETWORK_TIMEOUT_SECONDS,
    plugins: [cacheableResponse, new ExpirationPlugin(READ_CACHE_EXPIRATION)],
  }),
)
registerRoute(
  ({ url }) => url.pathname === '/api/invites/mine',
  new NetworkFirst({
    cacheName: 'api-invites-mine',
    networkTimeoutSeconds: NETWORK_TIMEOUT_SECONDS,
    plugins: [cacheableResponse, new ExpirationPlugin(READ_CACHE_EXPIRATION)],
  }),
)
// Defensive default: anything else under /api/ stays network-only until
// explicitly opted in above.
registerRoute(({ url }) => url.pathname.startsWith('/api/'), new NetworkOnly())

interface PushPayload {
  title: string
  body: string
  room_id: string
}

self.addEventListener('push', (event) => {
  if (!event.data) return
  let payload: PushPayload
  try {
    payload = event.data.json()
  } catch {
    return
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      data: { room_id: payload.room_id },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const roomId = (event.notification.data as { room_id?: string } | undefined)?.room_id
  const targetUrl = roomId ? `/rooms/${roomId}` : '/rooms'

  event.waitUntil(
    (async () => {
      const clientsList = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      for (const client of clientsList) {
        if ('focus' in client) {
          await client.navigate(targetUrl)
          return client.focus()
        }
      }
      return self.clients.openWindow(targetUrl)
    })(),
  )
})

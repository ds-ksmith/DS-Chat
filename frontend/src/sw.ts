/// <reference lib="webworker" />
import { CacheableResponsePlugin } from 'workbox-cacheable-response'
import { ExpirationPlugin } from 'workbox-expiration'
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { NetworkOnly, StaleWhileRevalidate } from 'workbox-strategies'

declare let self: ServiceWorkerGlobalScope

self.skipWaiting()
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

// Ported from Phase 3's vite.config.ts `workbox.runtimeCaching` -- that
// option only applies to the generateSW strategy, so with a hand-written
// service worker (required below for the push/notificationclick handlers)
// these routes have to be registered explicitly instead.
registerRoute(({ url }) => url.pathname.startsWith('/api/auth/'), new NetworkOnly())

registerRoute(
  ({ url }) => url.pathname === '/api/rooms/mine',
  new StaleWhileRevalidate({
    cacheName: 'api-rooms-mine',
    plugins: [cacheableResponse, new ExpirationPlugin(READ_CACHE_EXPIRATION)],
  }),
)
registerRoute(
  ({ url }) => url.pathname === '/api/rooms',
  new StaleWhileRevalidate({
    cacheName: 'api-rooms-open',
    plugins: [cacheableResponse, new ExpirationPlugin(READ_CACHE_EXPIRATION)],
  }),
)
registerRoute(
  ({ url }) => /^\/api\/rooms\/[^/]+\/messages$/.test(url.pathname),
  new StaleWhileRevalidate({
    cacheName: 'api-room-messages',
    plugins: [cacheableResponse, new ExpirationPlugin(READ_CACHE_EXPIRATION)],
  }),
)
registerRoute(
  ({ url }) => /^\/api\/rooms\/[^/]+\/members$/.test(url.pathname),
  new StaleWhileRevalidate({
    cacheName: 'api-room-members',
    plugins: [cacheableResponse, new ExpirationPlugin(READ_CACHE_EXPIRATION)],
  }),
)
registerRoute(
  ({ url }) => url.pathname === '/api/invites/mine',
  new StaleWhileRevalidate({
    cacheName: 'api-invites-mine',
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

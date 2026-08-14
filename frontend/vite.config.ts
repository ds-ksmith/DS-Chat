import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

const READ_CACHE_EXPIRATION = {
  maxEntries: 50,
  maxAgeSeconds: 7 * 24 * 60 * 60, // 7 days
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'KeepItTalking',
        short_name: 'Talking',
        start_url: '/',
        display: 'standalone',
        background_color: '#07080f', // --ds-void
        theme_color: '#101030', // --ds-surface
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icons/icon-512-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api/, /^\/ws/],
        // urlPattern uses function matchers against url.pathname rather than
        // RegExp (which Workbox tests against the *full href*, origin
        // included -- a `^/api/` anchor would silently never match).
        runtimeCaching: [
          // Never serve a stale cached "who am I" response.
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api/auth/'),
            handler: 'NetworkOnly',
          },
          // Cache-and-refresh: show the last known list/history immediately,
          // update from the network in the background. Routes default to
          // matching GET only, so mutations to these same paths are
          // untouched and still go straight to network.
          {
            urlPattern: ({ url }) => url.pathname === '/api/rooms/mine',
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-rooms-mine',
              expiration: READ_CACHE_EXPIRATION,
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: ({ url }) => url.pathname === '/api/rooms',
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-rooms-open',
              expiration: READ_CACHE_EXPIRATION,
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: ({ url }) =>
              /^\/api\/rooms\/[^/]+\/messages$/.test(url.pathname),
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-room-messages',
              expiration: READ_CACHE_EXPIRATION,
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: ({ url }) =>
              /^\/api\/rooms\/[^/]+\/members$/.test(url.pathname),
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-room-members',
              expiration: READ_CACHE_EXPIRATION,
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: ({ url }) => url.pathname === '/api/invites/mine',
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-invites-mine',
              expiration: READ_CACHE_EXPIRATION,
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          // Defensive default: anything else under /api/ (including any
          // future GET endpoint) stays network-only until explicitly opted
          // in above.
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api/'),
            handler: 'NetworkOnly',
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  // `vite preview` doesn't inherit `server.proxy` -- needed to exercise the
  // real production service worker (only registered against a built
  // bundle, not `vite dev`) against the actual backend.
  preview: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})

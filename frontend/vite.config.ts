import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// Single source of truth for the version shown in the app's About dialog --
// read at build time so it can never drift from what's actually released,
// rather than a separately-maintained string in the component itself.
const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'))

// https://vite.dev/config/
export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  plugins: [
    react(),
    VitePWA({
      // generateSW (Phase 3) can't add custom event listeners, and push /
      // notificationclick need exactly that -- injectManifest means we hand-
      // write the service worker (src/sw.ts); its runtime-caching routes are
      // registered there directly instead of via the `workbox` option below
      // (which only applies to generateSW).
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      injectManifest: {
        // Workbox's default globPatterns exclude the manifest's own output
        // dir, which is fine, but be explicit about what the app shell
        // precache should contain.
        globPatterns: ['**/*.{js,css,html,ico,png,svg,webmanifest}'],
      },
      // 'autoUpdate' silently activates a new service worker (and its
      // stale-relative-to-the-new-JS already-loaded page) with nothing
      // telling the user their currently-open tab has fallen behind --
      // 'prompt' leaves activation to an explicit updateServiceWorker()
      // call (UpdateBanner.tsx), so the user gets a "reload for the latest
      // version" banner instead of silently running old code indefinitely.
      registerType: 'prompt',
      manifest: {
        name: 'DS Chat',
        short_name: 'DS Chat',
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

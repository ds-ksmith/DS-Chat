import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
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

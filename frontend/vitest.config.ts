import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Deliberately separate from vite.config.ts, not an extension of it -- that
// file's VitePWA plugin does real build-time work (service worker
// injection, manifest generation) that has nothing to do with running unit
// tests and would just slow every test run down for no benefit.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
  },
})

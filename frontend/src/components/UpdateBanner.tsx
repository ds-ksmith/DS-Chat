import { useRegisterSW } from 'virtual:pwa-register/react'
import './UpdateBanner.css'

// The service worker (registerType: 'prompt', sw.ts) already installs and
// caches a new version silently in the background -- but a long-lived tab
// never navigates, and a page only checks for a new SW on navigation by
// default, so a tab left open for hours could sit on a stale check
// indefinitely. This polls explicitly so "reload available" shows up
// without the user having to close and reopen the app first.
const UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000

export function UpdateBanner() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, registration) {
      if (!registration) return
      setInterval(() => registration.update(), UPDATE_CHECK_INTERVAL_MS)
    },
  })

  if (!needRefresh) return null

  return (
    <div className="update-banner" role="status">
      <span>A new version of DS Chat is available.</span>
      <div className="update-banner-actions">
        <button type="button" className="btn-primary" onClick={() => updateServiceWorker(true)}>
          Reload
        </button>
        <button
          type="button"
          className="update-banner-dismiss"
          onClick={() => setNeedRefresh(false)}
          aria-label="Dismiss"
        >
          &times;
        </button>
      </div>
    </div>
  )
}

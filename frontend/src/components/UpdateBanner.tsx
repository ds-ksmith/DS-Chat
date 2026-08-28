import { useEffect } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { checkForUpdate, setSwRegistration } from '../lib/swUpdate'
import './UpdateBanner.css'

// The service worker (registerType: 'prompt', sw.ts) already installs and
// caches a new version silently in the background -- but a long-lived tab
// never navigates, and a page only checks for a new SW on navigation by
// default, so a tab left open for hours could sit on a stale check
// indefinitely. This polls explicitly so "reload available" shows up
// without the user having to close and reopen the app first. It's now a
// fallback, not the primary trigger -- useChatSocket.ts also calls
// checkForUpdate() on every WS reconnect, which reliably fires within
// seconds of a deploy (the backend restart that ships a new version also
// kills every open WS connection) rather than waiting up to an hour.
const UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000

export function UpdateBanner() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, registration) {
      if (!registration) return
      setSwRegistration(registration)
      setInterval(checkForUpdate, UPDATE_CHECK_INTERVAL_MS)
    },
  })

  useEffect(() => {
    // #58: a third trigger, alongside WS-reconnect and the hourly interval
    // above -- a tab backgrounded across a deploy gets checked the moment
    // someone actually looks at it again, rather than waiting on whichever
    // of those two happens to land first. Cheap insurance against either
    // one missing its moment (e.g. the reconnect-triggered check landing
    // during the same network blip that caused the reconnect, and failing
    // -- see checkForUpdate's own comment).
    function handleVisibilityChange() {
      if (document.visibilityState === 'visible') checkForUpdate()
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [])

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

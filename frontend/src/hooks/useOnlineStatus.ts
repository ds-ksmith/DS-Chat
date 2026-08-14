import { useEffect, useState } from 'react'

// navigator.onLine reflects the OS network interface, not whether our
// backend is actually reachable -- it can be true when the API is down. This
// is still a useful fast/cheap signal for a banner; the WebSocket
// `connected` state (see useChatSocket) is the more reliable one for
// whether live messaging actually works right now.
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(() => navigator.onLine)

  useEffect(() => {
    const goOnline = () => setOnline(true)
    const goOffline = () => setOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  return online
}

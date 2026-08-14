import { useOnlineStatus } from '../hooks/useOnlineStatus'
import './OfflineBanner.css'

export function OfflineBanner() {
  const online = useOnlineStatus()

  if (online) return null

  return (
    <div className="offline-banner" role="status">
      You're offline — showing cached data.
    </div>
  )
}

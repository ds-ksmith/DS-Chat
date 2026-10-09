import { useEffect, useState } from 'react'
import { isSameLocalDay } from '../lib/formatMessageTime'

function msUntilNextLocalMidnight(now: Date): number {
  // One second past, so the timer never lands a hair before midnight.
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 1)
  return next.getTime() - now.getTime()
}

// A `now` that only changes when the local calendar day does -- at midnight,
// and when a tab becomes visible again (a laptop that slept through
// midnight). Without it, a tab left open overnight keeps showing yesterday's
// messages as a bare "4:04 PM" until something unrelated rerenders the list.
export function useLocalDay(): Date {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>

    function refresh() {
      const current = new Date()
      // Same state object when the day hasn't changed, so no rerender.
      setNow((prev) => (isSameLocalDay(prev, current) ? prev : current))
    }

    function schedule() {
      timer = setTimeout(() => {
        refresh()
        schedule()
      }, msUntilNextLocalMidnight(new Date()))
    }

    function handleVisibilityChange() {
      if (document.visibilityState === 'visible') refresh()
    }

    schedule()
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [])

  return now
}

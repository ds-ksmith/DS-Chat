import { useEffect } from 'react'
import { notifyRoomOpened, notifyUnreadCount } from '../lib/desktopBridge'

// Tells the Electron desktop wrapper (a) when the user has genuinely
// entered a room, so it can clear that room's tray indicator, and (b) the
// current unread-room count, so the tray badge stays accurate. Both are
// no-ops in every browser build (see desktopBridge.ts).
//
// roomOpened must fire only on a genuine transition to a real room id --
// never merely because the window was shown, focused, restored, or opened
// from the tray, and never when no room is open at all. Depending on just
// the id (a primitive, not the room object) is what makes this safe to
// call from a component that rerenders often: an unrelated rerender that
// leaves activeRoomId unchanged doesn't rerun the effect, so there's no
// separate de-duplication to get wrong here -- it falls out of React's own
// effect-dependency comparison.
export function useDesktopRoomBridge(activeRoomId: string | undefined, unreadRoomCount: number): void {
  useEffect(() => {
    if (!activeRoomId) return
    notifyRoomOpened()
  }, [activeRoomId])

  useEffect(() => {
    notifyUnreadCount(unreadRoomCount)
  }, [unreadRoomCount])
}

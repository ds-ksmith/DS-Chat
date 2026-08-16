import { createContext, useCallback, useContext, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useChatSocket, type ChatSocketHandle } from '../ws/useChatSocket'

const ChatSocketContext = createContext<ChatSocketHandle | undefined>(undefined)

// One connection for the whole authenticated session, not just whichever
// page happens to be mounted -- previously this lived inside
// ChatShellPage, so navigating to a page that isn't ChatShellPage (e.g.
// /admin) unmounted it, closing the connection. The server correctly
// read that as "this user is no longer connected," which made a logged-in
// admin looking at the admin page show up as offline everywhere else
// (the presence dot reads this same connection).
export function ChatSocketProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const onUnauthenticated = useCallback(() => navigate('/login'), [navigate])
  const socket = useChatSocket({ onUnauthenticated })
  return <ChatSocketContext.Provider value={socket}>{children}</ChatSocketContext.Provider>
}

export function useChatSocketContext(): ChatSocketHandle {
  const ctx = useContext(ChatSocketContext)
  if (!ctx) throw new Error('useChatSocketContext must be used within a ChatSocketProvider')
  return ctx
}

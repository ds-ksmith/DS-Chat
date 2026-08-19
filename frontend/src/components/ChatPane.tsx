import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { NetworkError } from '../api/client'
import { getRoomMessages, markRoomRead } from '../api/rooms'
import type { ChatSocketHandle } from '../ws/useChatSocket'
import type { ChatMessageEnvelope, Message, MyRoomItem, RoomMember, ServerEnvelope } from '../types'
import { Composer } from './Composer'
import { MessageList } from './MessageList'
import './ChatPane.css'

interface ChatPaneProps {
  room: MyRoomItem
  rooms: MyRoomItem[]
  members: RoomMember[]
  isMobile: boolean
  onBack: () => void
  onToggleInfo: () => void
  infoOpen: boolean
  socket: ChatSocketHandle
  onRoomRead: (roomId: string) => void
}

export function ChatPane({
  room,
  rooms,
  members,
  isMobile,
  onBack,
  onToggleInfo,
  infoOpen,
  socket,
  onRoomRead,
}: ChatPaneProps) {
  const [history, setHistory] = useState<Message[]>([])
  const [live, setLive] = useState<ChatMessageEnvelope[]>([])
  const [wsError, setWsError] = useState<string | null>(null)
  const [historyUnavailableOffline, setHistoryUnavailableOffline] = useState(false)

  // refreshHistory fires more than once in quick succession on a fresh load
  // -- once from the mount effect below, then again as soon as the WS's
  // 'joined' envelope arrives (needed for the #37 rejoin-resync case). Nothing
  // guarantees those two requests *resolve* in the order they were sent --
  // the service worker's NetworkFirst cache (sw.ts) can fall back to a stale
  // cached response if one of them is slow, and a plain .then(setHistory)
  // would then let whichever response lands last win even if it's the older/
  // incomplete one. This tracks the latest-initiated request and ignores any
  // response that isn't from it, so a straggler can never overwrite a newer
  // result -- this was the actual cause of #45's "messages out of order on
  // reload" reports (confirmed no duplicate created_at timestamps in
  // production, ruling out a timestamp-precision cause).
  const historyRequestIdRef = useRef(0)

  const refreshHistory = useCallback(() => {
    // live is cleared alongside history, not just on room switch: it's
    // superseded by this fetch fully replacing history with the current
    // authoritative list, so anything already in live would otherwise
    // render twice once history was fetched.
    setLive([])
    setWsError(null)
    setHistoryUnavailableOffline(false)
    const requestId = ++historyRequestIdRef.current
    getRoomMessages(room.id)
      .then((msgs) => {
        if (historyRequestIdRef.current !== requestId) return
        setHistory(msgs)
      })
      .catch((err) => {
        if (historyRequestIdRef.current !== requestId) return
        if (err instanceof NetworkError) {
          setHistoryUnavailableOffline(true)
        } else {
          setWsError(String(err))
        }
      })
  }, [room.id])

  useEffect(() => {
    // Blanks the previous room's messages immediately, rather than leaving
    // them on screen until the fetch resolves -- refreshHistory itself
    // deliberately doesn't do this (a resync on the *same* room shouldn't
    // flash empty while refetching).
    setHistory([])
    refreshHistory()
  }, [room.id, refreshHistory])

  useEffect(() => {
    socket.joinRoom(room.id)
    return () => socket.leaveRoom(room.id)
  }, [socket, room.id])

  const markRead = useCallback(() => {
    // Live check, not a cached ref -- same reasoning as joinRoom's in
    // useChatSocket.ts: a backgrounded-but-open tab must keep accumulating
    // unread rather than auto-marking-read the instant a message arrives
    // somewhere it can't actually be seen.
    if (document.visibilityState !== 'visible') return
    onRoomRead(room.id)
    markRoomRead(room.id).catch(() => {
      // Best-effort -- an unread dot lagging by one message isn't worth
      // surfacing an error for; the next successful mark-read call (or a
      // future refreshRooms()) resyncs it.
    })
  }, [room.id, onRoomRead])

  useEffect(
    () =>
      // The socket is shared across every room this tab visits, so a
      // stray in-flight event for a room just left (or a different tab's
      // room, in theory) has to be filtered out here rather than assumed
      // away -- `error` has no room_id to filter on, but is rare enough
      // that misattributing one to the wrong room's banner isn't worth
      // guarding against separately.
      socket.subscribe((envelope: ServerEnvelope) => {
        if (envelope.type === 'joined' && envelope.room_id === room.id) {
          // Fires on initial join (a harmless redundant fetch right after
          // the mount effect's own) and, more importantly, on every
          // rejoin -- coming back from a backgrounded tab (see
          // useChatSocket's visibility handling) or reconnecting after a
          // dropped connection. Either way, messages could have arrived
          // while this socket wasn't in the room's channel, so resync
          // instead of trusting whatever's already in state.
          refreshHistory()
          markRead()
        } else if (envelope.type === 'message' && envelope.room_id === room.id) {
          setLive((prev) => [...prev, envelope])
          markRead()
        } else if (envelope.type === 'message_update' && envelope.room_id === room.id) {
          // link_preview only survives the edit if the URL it came from is
          // still there -- an edit that changed or removed it clears the
          // stale preview instead of leaving the old one showing. A new one
          // (if the new URL has any) arrives via its own 'link_preview'
          // envelope shortly after, same as a fresh send.
          setHistory((prev) =>
            prev.map((m) =>
              m.id === envelope.id
                ? {
                    ...m,
                    content: envelope.content,
                    edited_at: envelope.edited_at,
                    link_preview: m.link_preview?.url === envelope.preview_url ? m.link_preview : null,
                  }
                : m,
            ),
          )
          setLive((prev) =>
            prev.map((m) =>
              m.id === envelope.id
                ? {
                    ...m,
                    content: envelope.content,
                    edited_at: envelope.edited_at,
                    link_preview: m.link_preview?.url === envelope.preview_url ? m.link_preview : null,
                  }
                : m,
            ),
          )
        } else if (envelope.type === 'link_preview' && envelope.room_id === room.id) {
          const linkPreview = {
            url: envelope.url,
            title: envelope.title,
            description: envelope.description,
            image_url: envelope.image_url,
            site_name: envelope.site_name,
            is_image: envelope.is_image,
          }
          setHistory((prev) => prev.map((m) => (m.id === envelope.id ? { ...m, link_preview: linkPreview } : m)))
          setLive((prev) => prev.map((m) => (m.id === envelope.id ? { ...m, link_preview: linkPreview } : m)))
        } else if (envelope.type === 'reaction_update' && envelope.room_id === room.id) {
          setHistory((prev) =>
            prev.map((m) => (m.id === envelope.id ? { ...m, reactions: envelope.reactions } : m)),
          )
          setLive((prev) =>
            prev.map((m) => (m.id === envelope.id ? { ...m, reactions: envelope.reactions } : m)),
          )
        } else if (envelope.type === 'error') {
          setWsError(envelope.detail)
        }
      }),
    [socket, room.id, refreshHistory, markRead],
  )

  // history and live are just concatenated, not merge-sorted -- live is
  // strictly receipt order, which isn't always send order. A rejoin (a
  // reconnect, or opening the same room on another device) refetches
  // history but doesn't guarantee anything about the timing of whatever
  // WS messages land in live afterward relative to it, so without this
  // sort a message can render above one that was actually sent earlier.
  // Stable sort (guaranteed since ES2019) keeps same-timestamp messages in
  // their original relative order rather than shuffling them.
  const messages = useMemo(
    () =>
      [...history, ...live].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      ),
    [history, live],
  )

  // #47: name -> id for every room this user belongs to, so #roomname
  // references can resolve to a real link -- deliberately the viewer's own
  // rooms, not the sender's (see MessageContent.tsx's myRooms prop comment).
  const myRooms = useMemo(() => new Map(rooms.map((r) => [r.name, r.id])), [rooms])

  const connected = socket.connected
  const send = useCallback(
    (content: string, imageId?: string, fileId?: string) => socket.send(room.id, content, imageId, fileId),
    [socket, room.id],
  )
  const sendEdit = useCallback(
    (messageId: string, content: string) => socket.sendEdit(room.id, messageId, content),
    [socket, room.id],
  )
  const sendReaction = useCallback(
    (messageId: string, emoji: string) => socket.sendReaction(room.id, messageId, emoji),
    [socket, room.id],
  )

  return (
    <section className="chat-pane">
      <header className="chat-pane-header">
        {isMobile && (
          <button type="button" className="chat-pane-back" onClick={onBack} aria-label="Back to rooms">
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <polyline points="14,4 6,10 14,16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
        <div className="chat-pane-title-block">
          <div className="chat-pane-title">
            {room.dm_partner ? room.dm_partner.display_name || room.dm_partner.username : `#${room.name}`}
          </div>
          <div className="chat-pane-subtitle">
            {room.dm_partner
              ? room.dm_partner.status === 'online'
                ? 'Online'
                : 'Offline'
              : `${members.length} member${members.length === 1 ? '' : 's'}`}
          </div>
        </div>
        <button
          type="button"
          className={`chat-pane-info-btn${infoOpen ? ' chat-pane-info-btn-active' : ''}`}
          onClick={onToggleInfo}
          aria-label="Room details"
          aria-pressed={infoOpen}
        >
          <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
            <circle cx="10" cy="6.4" r="1" fill="currentColor" />
            <rect x="9" y="9" width="2" height="6" rx="1" fill="currentColor" />
          </svg>
        </button>
      </header>

      {wsError && <p className="chat-pane-error">{wsError}</p>}
      {historyUnavailableOffline && (
        <p className="chat-pane-error chat-pane-note">
          Message history for this room isn't available offline yet.
        </p>
      )}

      <MessageList
        roomId={room.id}
        messages={messages}
        members={members}
        myRooms={myRooms}
        onEdit={sendEdit}
        onReact={sendReaction}
      />
      <Composer
        roomId={room.id}
        roomName={room.dm_partner ? room.dm_partner.display_name || room.dm_partner.username : room.name}
        isDm={room.is_dm}
        members={members}
        rooms={rooms}
        disabled={!connected}
        onSend={send}
      />
    </section>
  )
}

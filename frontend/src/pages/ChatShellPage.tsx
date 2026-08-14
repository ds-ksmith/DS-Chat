import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { listMyInvites } from '../api/invites'
import { listMyRooms, listRoomMembers } from '../api/rooms'
import { BrowseRoomsModal } from '../components/BrowseRoomsModal'
import { ChatPane } from '../components/ChatPane'
import { InvitesModal } from '../components/InvitesModal'
import { NewRoomModal } from '../components/NewRoomModal'
import { RoomInfoPanel } from '../components/RoomInfoPanel'
import { Sidebar } from '../components/Sidebar'
import { TopBar } from '../components/TopBar'
import { MOBILE_BREAKPOINT, useWindowWidth } from '../hooks/useWindowWidth'
import type { MyRoomItem, RoomMember } from '../types'
import './ChatShellPage.css'

type ModalKind = 'new' | 'browse' | 'invites' | null

export function ChatShellPage() {
  const { roomId } = useParams<{ roomId?: string }>()
  const navigate = useNavigate()
  const width = useWindowWidth()
  const isMobile = width < MOBILE_BREAKPOINT

  const [rooms, setRooms] = useState<MyRoomItem[]>([])
  const [search, setSearch] = useState('')
  const [members, setMembers] = useState<RoomMember[]>([])
  const [inviteCount, setInviteCount] = useState(0)
  const [infoOpen, setInfoOpen] = useState(false)
  const [modal, setModal] = useState<ModalKind>(null)

  const activeRoom = rooms.find((r) => r.id === roomId)

  const refreshRooms = useCallback(async () => {
    const list = await listMyRooms()
    setRooms(list)
    return list
  }, [])

  const refreshMembers = useCallback(() => {
    if (!roomId) return
    listRoomMembers(roomId).then(setMembers).catch(() => setMembers([]))
  }, [roomId])

  useEffect(() => {
    refreshRooms().catch(() => {})
  }, [refreshRooms])

  useEffect(() => {
    listMyInvites()
      .then((list) => setInviteCount(list.length))
      .catch(() => {})
  }, [])

  useEffect(() => {
    refreshMembers()
  }, [refreshMembers])

  function goToRoom(id: string) {
    navigate(`/rooms/${id}`)
  }

  return (
    <div className="chat-shell">
      <TopBar />
      <div className="chat-shell-body">
        {(!isMobile || !roomId) && (
          <Sidebar
            rooms={rooms}
            activeRoomId={roomId}
            searchQuery={search}
            onSearchChange={setSearch}
            onOpenNewRoom={() => setModal('new')}
            onOpenBrowse={() => setModal('browse')}
            onOpenInvites={() => setModal('invites')}
            inviteCount={inviteCount}
          />
        )}

        {(!isMobile || roomId) &&
          (activeRoom ? (
            <ChatPane
              key={activeRoom.id}
              room={activeRoom}
              members={members}
              isMobile={isMobile}
              onBack={() => navigate('/rooms')}
              onToggleInfo={() => setInfoOpen((v) => !v)}
              infoOpen={infoOpen}
            />
          ) : (
            !isMobile && (
              <div className="chat-empty-state">
                <p>Select a room to start chatting.</p>
              </div>
            )
          ))}

        {!isMobile && infoOpen && activeRoom && (
          <RoomInfoPanel
            room={activeRoom}
            members={members}
            onClose={() => setInfoOpen(false)}
            onMembersChanged={refreshMembers}
            onRoomUpdated={() => refreshRooms()}
            onRoomDeleted={() => {
              setInfoOpen(false)
              navigate('/rooms')
              refreshRooms()
            }}
            onLeft={() => {
              setInfoOpen(false)
              navigate('/rooms')
              refreshRooms()
            }}
          />
        )}
      </div>

      {modal === 'new' && (
        <NewRoomModal
          onClose={() => setModal(null)}
          onCreated={(id) => {
            setModal(null)
            refreshRooms().then(() => goToRoom(id))
          }}
        />
      )}
      {modal === 'browse' && (
        <BrowseRoomsModal
          onClose={() => setModal(null)}
          onJoined={(id) => {
            setModal(null)
            refreshRooms().then(() => goToRoom(id))
          }}
        />
      )}
      {modal === 'invites' && (
        <InvitesModal
          onClose={() => setModal(null)}
          onInvitesChanged={setInviteCount}
          onAccepted={(id) => {
            setModal(null)
            refreshRooms().then(() => goToRoom(id))
          }}
        />
      )}
    </div>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { NetworkError } from '../api/client'
import { listMyRooms, listRoomMembers } from '../api/rooms'
import { BrowseRoomsModal } from '../components/BrowseRoomsModal'
import { ChatPane } from '../components/ChatPane'
import { NewRoomModal } from '../components/NewRoomModal'
import { OfflineBanner } from '../components/OfflineBanner'
import { RoomInfoPanel } from '../components/RoomInfoPanel'
import { Sidebar } from '../components/Sidebar'
import { TopBar } from '../components/TopBar'
import { useAuth } from '../context/AuthContext'
import { MOBILE_BREAKPOINT, useWindowWidth } from '../hooks/useWindowWidth'
import type { MyRoomItem, RoomMember } from '../types'
import './ChatShellPage.css'

type ModalKind = 'new' | 'browse' | null

export function ChatShellPage() {
  const { roomId } = useParams<{ roomId?: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const width = useWindowWidth()
  const isMobile = width < MOBILE_BREAKPOINT

  const [rooms, setRooms] = useState<MyRoomItem[]>([])
  const [search, setSearch] = useState('')
  const [members, setMembers] = useState<RoomMember[]>([])
  const [infoOpen, setInfoOpen] = useState(false)
  const [modal, setModal] = useState<ModalKind>(null)
  const [roomsUnavailableOffline, setRoomsUnavailableOffline] = useState(false)

  const activeRoom = rooms.find((r) => r.id === roomId)

  const refreshRooms = useCallback(async () => {
    try {
      const list = await listMyRooms()
      setRooms(list)
      setRoomsUnavailableOffline(false)
      return list
    } catch (err) {
      if (err instanceof NetworkError) {
        setRoomsUnavailableOffline(true)
        return []
      }
      throw err
    }
  }, [])

  const refreshMembers = useCallback(() => {
    if (!roomId) return
    listRoomMembers(roomId).then(setMembers).catch(() => setMembers([]))
  }, [roomId])

  useEffect(() => {
    refreshRooms().catch(() => {})
  }, [refreshRooms])

  useEffect(() => {
    refreshMembers()
    // Also re-run when the logged-in user's own profile changes (display
    // name/avatar) -- refreshMembers() itself doesn't change identity when
    // only roomId is the same, so without this the currently open room's
    // member list (and anything resolving avatar/name from it, like
    // MessageList) would keep showing the pre-edit profile until the room
    // is reopened.
  }, [refreshMembers, user?.display_name, user?.avatar_filename])

  function goToRoom(id: string) {
    navigate(`/rooms/${id}`)
  }

  return (
    <div className="chat-shell">
      <TopBar />
      <OfflineBanner />
      <div className="chat-shell-body">
        {(!isMobile || !roomId) && (
          <Sidebar
            rooms={rooms}
            activeRoomId={roomId}
            searchQuery={search}
            onSearchChange={setSearch}
            onOpenNewRoom={() => setModal('new')}
            onOpenBrowse={() => setModal('browse')}
            unavailableOffline={roomsUnavailableOffline && rooms.length === 0}
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

        {infoOpen && activeRoom && (
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
    </div>
  )
}

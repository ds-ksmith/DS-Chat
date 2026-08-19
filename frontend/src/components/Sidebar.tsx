import { useResizableWidth } from '../hooks/useResizableWidth'
import type { MyRoomItem } from '../types'
import { RoomRow } from './RoomRow'
import './Sidebar.css'

interface SidebarProps {
  rooms: MyRoomItem[]
  activeRoomId: string | undefined
  searchQuery: string
  onSearchChange: (value: string) => void
  onOpenNewRoom: () => void
  onOpenBrowse: () => void
  onOpenPeople: () => void
  unavailableOffline?: boolean
}

export function Sidebar({
  rooms,
  activeRoomId,
  searchQuery,
  onSearchChange,
  onOpenNewRoom,
  onOpenBrowse,
  onOpenPeople,
  unavailableOffline,
}: SidebarProps) {
  const query = searchQuery.trim().toLowerCase()
  const filtered = query ? rooms.filter((r) => r.name.toLowerCase().includes(query)) : rooms

  const { width, startResize } = useResizableWidth({
    storageKey: 'sidebar-width',
    defaultWidth: 300,
    min: 220,
    max: 480,
    anchor: 'left',
  })

  return (
    <aside className="sidebar" style={{ width }}>
      <div className="sidebar-resize-handle" onPointerDown={startResize} />
      <div className="sidebar-toolbar">
        <div className="sidebar-search">
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.6" />
            <line x1="12.5" y1="12.5" x2="17" y2="17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          <input
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search"
            aria-label="Search rooms"
          />
        </div>
        <button type="button" className="sidebar-icon-btn" onClick={onOpenNewRoom} aria-label="New room" title="New room">
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <line x1="7" y1="1" x2="7" y2="13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <line x1="1" y1="7" x2="13" y2="7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <div className="sidebar-scroll">
        <button type="button" className="sidebar-entry" onClick={onOpenBrowse}>
          <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <circle cx="9" cy="9" r="6" />
            <line x1="13.5" y1="13.5" x2="18" y2="18" strokeLinecap="round" />
          </svg>
          Browse rooms
        </button>
        <button type="button" className="sidebar-entry" onClick={onOpenPeople}>
          <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <circle cx="7" cy="6.5" r="3" />
            <path d="M2 17c0-3 2.5-5 5-5s5 2 5 5" strokeLinecap="round" />
            <circle cx="14.5" cy="7.5" r="2.3" />
            <path d="M12.7 12.3c2-.3 4 1.2 4.8 3.7" strokeLinecap="round" />
          </svg>
          People
        </button>

        {unavailableOffline ? (
          <p className="sidebar-offline-note">
            Your rooms aren't available offline yet. Reconnect to load them.
          </p>
        ) : (
          <>
            {filtered.length > 0 && <div className="sidebar-section-label">Rooms</div>}
            <nav>
              {filtered.map((room, i) => (
                <RoomRow
                  key={room.id}
                  room={room}
                  colorIndex={i}
                  active={room.id === activeRoomId}
                />
              ))}
            </nav>
          </>
        )}
      </div>
    </aside>
  )
}

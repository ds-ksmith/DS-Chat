import { useState } from 'react'
import { useResizableWidth } from '../hooks/useResizableWidth'
import type { MyRoomItem } from '../types'
import { RoomRow } from './RoomRow'
import './Sidebar.css'

// #62: which of the two sections (keyed 'dm'/'rooms') are collapsed --
// persisted the same way sidebar-width already is (see useResizableWidth),
// a per-viewer cosmetic preference with no reason to live server-side.
const COLLAPSED_SECTIONS_KEY = 'sidebar-collapsed-sections'

function loadCollapsedSections(): Set<string> {
  try {
    const raw = localStorage.getItem(COLLAPSED_SECTIONS_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? new Set(parsed.filter((s) => typeof s === 'string')) : new Set()
  } catch {
    return new Set()
  }
}

function saveCollapsedSections(sections: Set<string>): void {
  try {
    localStorage.setItem(COLLAPSED_SECTIONS_KEY, JSON.stringify([...sections]))
  } catch {
    // storage unavailable (private browsing, quota) -- collapse state just
    // won't persist this session, not fatal.
  }
}

interface SidebarSectionHeaderProps {
  label: string
  collapsed: boolean
  onToggle: () => void
}

function SidebarSectionHeader({ label, collapsed, onToggle }: SidebarSectionHeaderProps) {
  return (
    <button type="button" className="sidebar-section-label" onClick={onToggle} aria-expanded={!collapsed}>
      <svg
        className={`sidebar-section-chevron${collapsed ? ' sidebar-section-chevron-collapsed' : ''}`}
        width="10"
        height="10"
        viewBox="0 0 10 10"
        aria-hidden="true"
      >
        <path
          d="M2 3.5 5 7 8 3.5"
          stroke="currentColor"
          strokeWidth="1.4"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {label}
    </button>
  )
}

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
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(loadCollapsedSections)

  function toggleSection(key: string) {
    setCollapsedSections((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      saveCollapsedSections(next)
      return next
    })
  }

  const query = searchQuery.trim().toLowerCase()
  // A DM's `name` is an internal token, never what a user would search for
  // -- matched against the partner's display name/username instead.
  function matchesQuery(room: MyRoomItem): boolean {
    if (!query) return true
    if (room.is_dm && room.dm_partner) {
      return (
        (room.dm_partner.display_name ?? '').toLowerCase().includes(query) ||
        room.dm_partner.username.toLowerCase().includes(query)
      )
    }
    return room.name.toLowerCase().includes(query)
  }
  // #57: archived rooms keep flowing through in `rooms` (so a member who
  // still has one open via a direct link resolves fine -- see ChatPane),
  // but they're a dead end going forward, so they don't belong in the list
  // you'd browse/search from.
  const filtered = rooms.filter((r) => !r.is_archived).filter(matchesQuery)
  const directMessages = filtered.filter((r) => r.is_dm)
  const regularRooms = filtered.filter((r) => !r.is_dm)

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
            {directMessages.length > 0 && (
              <>
                <SidebarSectionHeader
                  label="Direct Messages"
                  collapsed={collapsedSections.has('dm')}
                  onToggle={() => toggleSection('dm')}
                />
                {!collapsedSections.has('dm') && (
                  <nav>
                    {directMessages.map((room, i) => (
                      <RoomRow
                        key={room.id}
                        room={room}
                        colorIndex={i}
                        active={room.id === activeRoomId}
                      />
                    ))}
                  </nav>
                )}
              </>
            )}
            {regularRooms.length > 0 && (
              <>
                <SidebarSectionHeader
                  label="Rooms"
                  collapsed={collapsedSections.has('rooms')}
                  onToggle={() => toggleSection('rooms')}
                />
                {!collapsedSections.has('rooms') && (
                  <nav>
                    {regularRooms.map((room, i) => (
                      <RoomRow
                        key={room.id}
                        room={room}
                        colorIndex={i}
                        active={room.id === activeRoomId}
                      />
                    ))}
                  </nav>
                )}
              </>
            )}
          </>
        )}
      </div>
    </aside>
  )
}

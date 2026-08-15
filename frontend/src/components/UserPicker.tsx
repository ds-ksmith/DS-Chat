import { useEffect, useRef, useState } from 'react'
import { getUserAvatarUrl } from '../api/users'
import type { UserDirectoryEntry } from '../types'
import { UserAvatar } from './UserAvatar'
import './UserPicker.css'

interface UserPickerProps {
  users: UserDirectoryEntry[]
  excludeUserIds?: string[]
  placeholder?: string
  onSelect: (user: UserDirectoryEntry) => void
}

export function UserPicker({ users, excludeUserIds, placeholder = 'Search users…', onSelect }: UserPickerProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)

  const excluded = new Set(excludeUserIds ?? [])
  const q = query.trim().toLowerCase()
  const matches = q
    ? users
        .filter((u) => !excluded.has(u.id))
        .filter((u) => u.username.toLowerCase().includes(q) || (u.display_name ?? '').toLowerCase().includes(q))
        .slice(0, 8)
    : []

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function choose(u: UserDirectoryEntry) {
    onSelect(u)
    setQuery('')
    setOpen(false)
    setHighlighted(0)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!open || matches.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlighted((h) => Math.min(h + 1, matches.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlighted((h) => Math.max(h - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      choose(matches[highlighted])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="user-picker" ref={rootRef}>
      <input
        type="text"
        placeholder={placeholder}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
          setHighlighted(0)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
      />
      {open && matches.length > 0 && (
        <div className="user-picker-dropdown">
          {matches.map((u, i) => (
            <button
              type="button"
              key={u.id}
              className={`user-picker-row${i === highlighted ? ' user-picker-row-active' : ''}`}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(u)}
              onMouseEnter={() => setHighlighted(i)}
            >
              <UserAvatar
                username={u.username}
                colorIndex={i}
                size={22}
                avatarUrl={u.avatar_filename ? getUserAvatarUrl(u.id, u.avatar_filename) : null}
              />
              <span className="user-picker-row-name">{u.display_name || u.username}</span>
              {u.display_name && <span className="user-picker-row-username">@{u.username}</span>}
            </button>
          ))}
        </div>
      )}
      {open && q && matches.length === 0 && <div className="user-picker-dropdown user-picker-empty">No matches</div>}
    </div>
  )
}

import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { createRoom, joinRoom, listRooms } from '../api/rooms'
import { RoomListItem } from '../components/RoomListItem'
import { useAuth } from '../context/AuthContext'
import type { RoomListItem as RoomListItemType } from '../types'

export function RoomListPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [rooms, setRooms] = useState<RoomListItemType[]>([])
  const [newRoomName, setNewRoomName] = useState('')
  const [joiningId, setJoiningId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    setRooms(await listRooms())
  }

  useEffect(() => {
    refresh().catch((err) => setError(String(err)))
  }, [])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    const name = newRoomName.trim()
    if (!name) return
    setError(null)
    try {
      await createRoom(name)
      setNewRoomName('')
      await refresh()
    } catch (err) {
      setError(String(err))
    }
  }

  async function handleJoin(roomId: string) {
    setJoiningId(roomId)
    setError(null)
    try {
      await joinRoom(roomId)
      await refresh()
      navigate(`/rooms/${roomId}`)
    } catch (err) {
      setError(String(err))
    } finally {
      setJoiningId(null)
    }
  }

  return (
    <div style={{ maxWidth: 480, margin: '2rem auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Rooms</h1>
        <div>
          <span style={{ marginRight: '1rem' }}>{user?.username}</span>
          <button onClick={() => logout()}>Log out</button>
        </div>
      </header>

      <form onSubmit={handleCreate} style={{ display: 'flex', gap: '0.5rem', margin: '1rem 0' }}>
        <input
          value={newRoomName}
          onChange={(e) => setNewRoomName(e.target.value)}
          placeholder="New room name"
        />
        <button type="submit">Create</button>
      </form>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      <ul style={{ listStyle: 'none', padding: 0 }}>
        {rooms.map((room) => (
          <RoomListItem
            key={room.id}
            room={room}
            onJoin={handleJoin}
            joining={joiningId === room.id}
          />
        ))}
      </ul>
    </div>
  )
}

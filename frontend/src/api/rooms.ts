import { apiFetch } from './client'
import type { Message, Room, RoomListItem } from '../types'

export function listRooms(): Promise<RoomListItem[]> {
  return apiFetch<RoomListItem[]>('/api/rooms')
}

export function createRoom(name: string, description?: string): Promise<Room> {
  return apiFetch<Room>('/api/rooms', {
    method: 'POST',
    body: JSON.stringify({ name, description: description || null }),
  })
}

export function joinRoom(roomId: string): Promise<Room> {
  return apiFetch<Room>(`/api/rooms/${roomId}/join`, { method: 'POST' })
}

export function getRoomMessages(roomId: string): Promise<Message[]> {
  return apiFetch<Message[]>(`/api/rooms/${roomId}/messages`)
}

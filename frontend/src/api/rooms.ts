import { apiFetch } from './client'
import type { Message, MyRoomItem, Room, RoomListItem, RoomMember, RoomRole } from '../types'

export function listRooms(): Promise<RoomListItem[]> {
  return apiFetch<RoomListItem[]>('/api/rooms')
}

export function listMyRooms(): Promise<MyRoomItem[]> {
  return apiFetch<MyRoomItem[]>('/api/rooms/mine')
}

export function createRoom(
  name: string,
  description?: string,
  isPrivate = false,
): Promise<Room> {
  return apiFetch<Room>('/api/rooms', {
    method: 'POST',
    body: JSON.stringify({ name, description: description || null, is_private: isPrivate }),
  })
}

export function updateRoom(
  roomId: string,
  data: { name?: string; description?: string },
): Promise<Room> {
  return apiFetch<Room>(`/api/rooms/${roomId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteRoom(roomId: string): Promise<void> {
  return apiFetch<void>(`/api/rooms/${roomId}`, { method: 'DELETE' })
}

export function joinRoom(roomId: string): Promise<Room> {
  return apiFetch<Room>(`/api/rooms/${roomId}/join`, { method: 'POST' })
}

export function leaveRoom(roomId: string): Promise<void> {
  return apiFetch<void>(`/api/rooms/${roomId}/leave`, { method: 'POST' })
}

export function listRoomMembers(roomId: string): Promise<RoomMember[]> {
  return apiFetch<RoomMember[]>(`/api/rooms/${roomId}/members`)
}

export function removeMember(roomId: string, userId: string): Promise<void> {
  return apiFetch<void>(`/api/rooms/${roomId}/members/${userId}`, { method: 'DELETE' })
}

export function changeMemberRole(
  roomId: string,
  userId: string,
  role: RoomRole,
): Promise<RoomMember> {
  return apiFetch<RoomMember>(`/api/rooms/${roomId}/members/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  })
}

export function transferOwnership(roomId: string, newOwnerUserId: string): Promise<Room> {
  return apiFetch<Room>(`/api/rooms/${roomId}/transfer-ownership`, {
    method: 'POST',
    body: JSON.stringify({ new_owner_user_id: newOwnerUserId }),
  })
}

export function getRoomMessages(roomId: string): Promise<Message[]> {
  return apiFetch<Message[]>(`/api/rooms/${roomId}/messages`)
}

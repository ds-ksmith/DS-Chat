import { apiFetch, ApiError, NetworkError } from './client'
import type {
  Message,
  MessageFileInfo,
  MyRoomItem,
  Room,
  RoomAttachment,
  RoomListItem,
  RoomMember,
  RoomRole,
} from '../types'

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

// #52: find-or-create -- returns the existing DM with this person if one
// already exists, rather than always creating a new room.
export function startDm(otherUserId: string): Promise<Room> {
  return apiFetch<Room>('/api/rooms/dm', {
    method: 'POST',
    body: JSON.stringify({ other_user_id: otherUserId }),
  })
}

export function updateRoom(
  roomId: string,
  data: { name?: string; description?: string; is_private?: boolean },
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

export function listRoomAttachments(roomId: string): Promise<RoomAttachment[]> {
  return apiFetch<RoomAttachment[]>(`/api/rooms/${roomId}/attachments`)
}

export function markRoomRead(roomId: string): Promise<void> {
  return apiFetch<void>(`/api/rooms/${roomId}/read`, { method: 'POST' })
}

export function addRoomMember(roomId: string, userId: string): Promise<RoomMember> {
  return apiFetch<RoomMember>(`/api/rooms/${roomId}/members`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId }),
  })
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

// Not apiFetch: that wrapper always sets Content-Type: application/json,
// which would stomp the multipart boundary the browser needs to set itself
// for a file upload.
export async function uploadRoomImage(roomId: string, file: File): Promise<{ id: string }> {
  const formData = new FormData()
  formData.append('file', file)

  let response: Response
  try {
    response = await fetch(`/api/rooms/${roomId}/images`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    })
  } catch {
    throw new NetworkError()
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // response had no JSON body
    }
    throw new ApiError(response.status, detail)
  }

  return (await response.json()) as { id: string }
}

export function getRoomImageUrl(roomId: string, imageId: string): string {
  return `/api/rooms/${roomId}/images/${imageId}`
}

// Not apiFetch, same multipart-boundary reason as uploadRoomImage.
export async function uploadRoomFile(roomId: string, file: File): Promise<MessageFileInfo> {
  const formData = new FormData()
  formData.append('file', file)

  let response: Response
  try {
    response = await fetch(`/api/rooms/${roomId}/files`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    })
  } catch {
    throw new NetworkError()
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // response had no JSON body
    }
    throw new ApiError(response.status, detail)
  }

  return (await response.json()) as MessageFileInfo
}

export function getRoomFileUrl(roomId: string, fileId: string): string {
  return `/api/rooms/${roomId}/files/${fileId}`
}

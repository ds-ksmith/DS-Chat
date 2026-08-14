import { apiFetch } from './client'
import type { Invite, MyInvite, RoomMember } from '../types'

export function createInvite(roomId: string, targetUsername: string): Promise<Invite> {
  return apiFetch<Invite>(`/api/rooms/${roomId}/invites`, {
    method: 'POST',
    body: JSON.stringify({ target_username: targetUsername }),
  })
}

export function listRoomInvites(roomId: string): Promise<Invite[]> {
  return apiFetch<Invite[]>(`/api/rooms/${roomId}/invites`)
}

export function revokeInvite(roomId: string, inviteId: string): Promise<void> {
  return apiFetch<void>(`/api/rooms/${roomId}/invites/${inviteId}`, { method: 'DELETE' })
}

export function listMyInvites(): Promise<MyInvite[]> {
  return apiFetch<MyInvite[]>('/api/invites/mine')
}

export function acceptInvite(inviteId: string): Promise<RoomMember> {
  return apiFetch<RoomMember>(`/api/invites/${inviteId}/accept`, { method: 'POST' })
}

export function declineInvite(inviteId: string): Promise<Invite> {
  return apiFetch<Invite>(`/api/invites/${inviteId}/decline`, { method: 'POST' })
}

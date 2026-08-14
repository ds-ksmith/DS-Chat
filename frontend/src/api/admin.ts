import { apiFetch } from './client'
import type { AdminRoom, AdminUser, AuditLogEntry } from '../types'

export function listAdminUsers(): Promise<AdminUser[]> {
  return apiFetch<AdminUser[]>('/api/admin/users')
}

export function deactivateUser(userId: string): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/api/admin/users/${userId}/deactivate`, { method: 'POST' })
}

export function reactivateUser(userId: string): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/api/admin/users/${userId}/reactivate`, { method: 'POST' })
}

export function resetUserPassword(userId: string, newPassword: string): Promise<void> {
  return apiFetch<void>(`/api/admin/users/${userId}/reset-password`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  })
}

export function promoteUser(userId: string): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/api/admin/users/${userId}/promote`, { method: 'POST' })
}

export function demoteUser(userId: string): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/api/admin/users/${userId}/demote`, { method: 'POST' })
}

export function listAdminRooms(): Promise<AdminRoom[]> {
  return apiFetch<AdminRoom[]>('/api/admin/rooms')
}

export function archiveRoom(roomId: string): Promise<AdminRoom> {
  return apiFetch<AdminRoom>(`/api/admin/rooms/${roomId}/archive`, { method: 'POST' })
}

export function unarchiveRoom(roomId: string): Promise<AdminRoom> {
  return apiFetch<AdminRoom>(`/api/admin/rooms/${roomId}/unarchive`, { method: 'POST' })
}

export function transferOwnershipAdmin(roomId: string, newOwnerId: string): Promise<AdminRoom> {
  return apiFetch<AdminRoom>(`/api/admin/rooms/${roomId}/transfer-ownership`, {
    method: 'POST',
    body: JSON.stringify({ new_owner_id: newOwnerId }),
  })
}

export function listAuditLog(limit = 50, offset = 0): Promise<AuditLogEntry[]> {
  return apiFetch<AuditLogEntry[]>(`/api/admin/audit-log?limit=${limit}&offset=${offset}`)
}

import { apiFetch } from './client'
import type {
  AdminRoom,
  AdminUser,
  AuditLogEntry,
  EventSubscriptionAdmin,
  SiteInvite,
  SmtpSettings,
  WebhookIncomingAdmin,
} from '../types'

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

export function listAllIncomingWebhooks(): Promise<WebhookIncomingAdmin[]> {
  return apiFetch<WebhookIncomingAdmin[]>('/api/admin/webhooks/incoming')
}

export function listAllEventSubscriptions(): Promise<EventSubscriptionAdmin[]> {
  return apiFetch<EventSubscriptionAdmin[]>('/api/admin/event-subscriptions')
}

export function inviteUser(email: string): Promise<SiteInvite> {
  return apiFetch<SiteInvite>('/api/admin/invites', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function listSiteInvites(): Promise<SiteInvite[]> {
  return apiFetch<SiteInvite[]>('/api/admin/invites')
}

export function revokeSiteInvite(inviteId: string): Promise<SiteInvite> {
  return apiFetch<SiteInvite>(`/api/admin/invites/${inviteId}`, { method: 'DELETE' })
}

export function getSmtpSettings(): Promise<SmtpSettings | null> {
  return apiFetch<SmtpSettings | null>('/api/admin/settings/smtp')
}

export interface SmtpSettingsPayload {
  host: string
  port: number
  username?: string | null
  password?: string | null
  from_address: string
  use_tls: boolean
}

export function updateSmtpSettings(payload: SmtpSettingsPayload): Promise<SmtpSettings> {
  return apiFetch<SmtpSettings>('/api/admin/settings/smtp', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function sendTestSmtpEmail(): Promise<void> {
  return apiFetch<void>('/api/admin/settings/smtp/test', { method: 'POST' })
}

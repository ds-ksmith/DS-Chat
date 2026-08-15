export interface User {
  id: string
  username: string
  email: string
  is_bot: boolean
  is_site_admin: boolean
  display_name: string | null
  avatar_filename: string | null
  created_at: string
}

export interface UserDirectoryEntry {
  id: string
  username: string
  display_name: string | null
  avatar_filename: string | null
}

export type RoomRole = 'owner' | 'admin' | 'member'

export interface Room {
  id: string
  name: string
  description: string | null
  is_private: boolean
  owner_id: string
  created_at: string
}

export interface RoomListItem extends Room {
  is_member: boolean
}

export interface MyRoomItem extends Room {
  role: RoomRole
}

export interface RoomMember {
  user_id: string
  username: string
  display_name: string | null
  avatar_filename: string | null
  role: RoomRole
  joined_at: string
}

export type InviteStatus = 'pending' | 'accepted' | 'revoked'

export interface ReactionSummary {
  emoji: string
  count: number
  user_ids: string[]
}

export interface MessageFileInfo {
  id: string
  filename: string
  size_bytes: number
  content_type: string
}

export interface Message {
  id: string
  room_id: string
  user_id: string
  username: string
  content: string | null
  image_id: string | null
  file: MessageFileInfo | null
  reactions: ReactionSummary[]
  created_at: string
  edited_at: string | null
}

export interface ChatMessageEnvelope {
  type: 'message'
  id: string
  room_id: string
  user_id: string
  username: string
  content: string | null
  image_id: string | null
  file: MessageFileInfo | null
  reactions: ReactionSummary[]
  created_at: string
  edited_at: string | null
}

export interface ChatMessageUpdateEnvelope {
  type: 'message_update'
  id: string
  room_id: string
  content: string
  edited_at: string | null
}

export interface ChatReactionUpdateEnvelope {
  type: 'reaction_update'
  id: string
  room_id: string
  reactions: ReactionSummary[]
}

export interface ChatJoinedEnvelope {
  type: 'joined'
  room_id: string
}

export interface ChatErrorEnvelope {
  type: 'error'
  detail: string
}

export type ServerEnvelope =
  | ChatMessageEnvelope
  | ChatMessageUpdateEnvelope
  | ChatReactionUpdateEnvelope
  | ChatJoinedEnvelope
  | ChatErrorEnvelope

export interface AdminUser {
  id: string
  username: string
  email: string
  is_bot: boolean
  is_site_admin: boolean
  is_active: boolean
  display_name: string | null
  avatar_filename: string | null
  created_at: string
}

export interface AdminRoom {
  id: string
  name: string
  description: string | null
  is_private: boolean
  is_archived: boolean
  owner_id: string
  created_at: string
  member_count: number
}

export interface AuditLogEntry {
  id: string
  actor_id: string
  actor_username: string
  action: string
  target_type: string
  target_id: string
  metadata: Record<string, unknown> | null
  created_at: string
}

export type ApiScope = 'read:messages' | 'write:messages' | 'manage:rooms'

export interface Bot {
  id: string
  username: string
  is_active: boolean
  created_at: string
}

export interface ApiToken {
  id: string
  owner_id: string
  scopes: ApiScope[]
  last_used_at: string | null
  created_at: string
}

export interface ApiTokenCreated extends ApiToken {
  token: string
}

export interface WebhookIncoming {
  id: string
  room_id: string
  token: string
  created_by: string
  description: string | null
  created_at: string
}

export interface WebhookIncomingAdmin extends WebhookIncoming {
  room_name: string
  created_by_username: string
}

export type EventType = 'message.created' | 'message.updated'

export interface EventSubscription {
  id: string
  room_id: string | null
  event_types: EventType[]
  target_url: string
  created_by: string
  created_at: string
}

export interface EventSubscriptionCreated extends EventSubscription {
  signing_secret: string
}

export interface EventSubscriptionAdmin extends EventSubscription {
  room_name: string | null
  created_by_username: string
}

export interface SiteInvite {
  id: string
  email: string
  invited_by: string
  status: InviteStatus
  expires_at: string
  created_at: string
}

export interface SmtpSettings {
  host: string
  port: number
  username: string | null
  has_password: boolean
  from_address: string
  use_tls: boolean
  updated_at: string
}

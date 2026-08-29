export type ThemeName = 'dark' | 'light' | 'midnight' | 'sunset' | 'custom'

// Matches exactly the CSS custom properties frontend/src/styles/themes.css
// overrides per built-in preset -- kept in sync with
// backend/app/schemas/custom_theme.py's CustomThemeColors.
export interface CustomThemeColors {
  void: string
  void_2: string
  surface: string
  surface_2: string
  border: string
  text: string
  muted: string
  accent: string
  accent_2: string
  accent_3: string
  highlight: string
  danger: string
  color_scheme: 'light' | 'dark'
}

export interface CustomTheme {
  id: string
  name: string
  colors: CustomThemeColors
  created_at: string
}

export interface User {
  id: string
  username: string
  email: string
  is_bot: boolean
  is_site_admin: boolean
  display_name: string | null
  theme: ThemeName | null
  // Only non-null when theme === 'custom' -- see UserRead's model_validator
  // in backend/app/schemas/user.py.
  active_custom_theme: CustomTheme | null
  avatar_filename: string | null
  appear_offline: boolean
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
  is_dm: boolean
  // #57: exposed here (not just the admin-only AdminRoom) so a member who
  // still has this room -- direct link, or before their sidebar list next
  // refreshes -- can be shown it's read-only instead of just silently
  // failing to send.
  is_archived: boolean
  owner_id: string
  created_at: string
}

export interface RoomListItem extends Room {
  is_member: boolean
}

export interface DmPartnerInfo {
  user_id: string
  username: string
  display_name: string | null
  avatar_filename: string | null
  status: 'online' | 'offline'
}

export interface MyRoomItem extends Room {
  role: RoomRole
  has_unread: boolean
  // Unread and mentions the current user -- takes visual priority over
  // has_unread in the sidebar (see RoomRow.tsx), not shown alongside it.
  has_mention: boolean
  // #52: the other participant, only for is_dm rooms -- see backend
  // schemas/room.py's MyRoomItem for why this is precomputed server-side.
  dm_partner: DmPartnerInfo | null
  // #67: this viewer's own opt-in for email while offline -- the room's
  // first unread message plus every mention (see backend's
  // message_events.py). Always false for a DM.
  email_notifications: boolean
}

export interface RoomMember {
  user_id: string
  username: string
  display_name: string | null
  avatar_filename: string | null
  role: RoomRole
  joined_at: string
  status: 'online' | 'offline'
}

export interface RoomAttachment {
  id: string
  kind: 'file' | 'image'
  filename: string | null
  content_type: string
  size_bytes: number
  uploaded_by: string
  message_id: string
  created_at: string
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

export interface LinkPreviewInfo {
  url: string
  title: string | null
  description: string | null
  image_url: string | null
  site_name: string | null
  // A direct link to an image file -- render the image itself (like a real
  // attachment) rather than the small title+description unfurl card.
  is_image: boolean
}

export interface Message {
  id: string
  room_id: string
  user_id: string
  username: string
  content: string | null
  image_id: string | null
  file: MessageFileInfo | null
  link_preview: LinkPreviewInfo | null
  reactions: ReactionSummary[]
  created_at: string
  edited_at: string | null
  // #53: null for a live message. content/image_id/file/link_preview are
  // already cleared server-side once this is set -- MessageList renders a
  // tombstone off this alone rather than inferring deletion from the rest
  // being empty.
  deleted_at: string | null
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
  link_preview: LinkPreviewInfo | null
  reactions: ReactionSummary[]
  created_at: string
  edited_at: string | null
  // Always null here -- a just-sent message can't already be deleted --
  // but declared so MessageList can read msg.deleted_at uniformly across
  // the Message | ChatMessageEnvelope union, same as edited_at above.
  deleted_at: string | null
}

export interface ChatMessageUpdateEnvelope {
  type: 'message_update'
  id: string
  room_id: string
  content: string
  edited_at: string | null
  // Lets the frontend clear a stale preview when an edit changes/removes
  // the URL it came from -- compare against whatever link_preview.url the
  // message currently has rather than assuming it's still valid.
  preview_url: string | null
}

export interface ChatLinkPreviewEnvelope {
  type: 'link_preview'
  id: string
  room_id: string
  url: string
  title: string | null
  description: string | null
  image_url: string | null
  site_name: string | null
  is_image: boolean
}

export interface ChatReactionUpdateEnvelope {
  type: 'reaction_update'
  id: string
  room_id: string
  reactions: ReactionSummary[]
}

export interface ChatMessageDeletedEnvelope {
  type: 'message_deleted'
  id: string
  room_id: string
}

export interface ChatJoinedEnvelope {
  type: 'joined'
  room_id: string
}

export interface ChatErrorEnvelope {
  type: 'error'
  detail: string
}

export interface ChatRoomAddedEnvelope {
  type: 'room_added'
  room_id: string
}

export interface ChatMemberUpdatedEnvelope {
  type: 'member_updated'
  room_id: string
  user_id: string
}

export interface ChatUnreadUpdateEnvelope {
  type: 'unread_update'
  room_id: string
  mentioned: boolean
}

// #63: sent on the recipient's own per-user channel, one per DM partner,
// whenever that partner's global online/offline state changes -- lets the
// sidebar's presence dot (MyRoomItem.dm_partner.status) stay live without
// needing that DM to be the currently open room (member_updated's
// room-channel delivery doesn't reach an unopened DM at all).
export interface ChatDmPresenceUpdateEnvelope {
  type: 'dm_presence_update'
  user_id: string
  status: 'online' | 'offline'
}

// #49: delivered over this same socket, alongside the existing Web Push
// send, to every eligible offline member regardless of push-subscription
// status -- see backend/app/services/message_events.py's
// _notify_offline_members. `id` is the source message's own id (stable,
// not random) so the desktop bridge's dedup can key on it across socket
// reconnects/replays.
export interface ChatDesktopNotificationEnvelope {
  type: 'desktop_notification'
  id: string
  room_id: string
  title: string
  body: string
}

export type ServerEnvelope =
  | ChatMessageEnvelope
  | ChatMessageUpdateEnvelope
  | ChatReactionUpdateEnvelope
  | ChatMessageDeletedEnvelope
  | ChatLinkPreviewEnvelope
  | ChatJoinedEnvelope
  | ChatErrorEnvelope
  | ChatRoomAddedEnvelope
  | ChatMemberUpdatedEnvelope
  | ChatUnreadUpdateEnvelope
  | ChatDesktopNotificationEnvelope
  | ChatDmPresenceUpdateEnvelope

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

export interface UploadSettings {
  max_upload_bytes: number
  updated_at: string
}

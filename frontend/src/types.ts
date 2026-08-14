export interface User {
  id: string
  username: string
  email: string
  is_bot: boolean
  is_site_admin: boolean
  created_at: string
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
  role: RoomRole
  joined_at: string
}

export type InviteStatus = 'pending' | 'accepted' | 'revoked'

export interface Invite {
  id: string
  room_id: string
  invited_by: string
  target_user_id: string | null
  target_username: string | null
  status: InviteStatus
  expires_at: string
  created_at: string
}

export interface MyInvite extends Invite {
  room_name: string
  invited_by_username: string
}

export interface Message {
  id: string
  room_id: string
  user_id: string
  username: string
  content: string
  created_at: string
}

export interface ChatMessageEnvelope {
  type: 'message'
  id: string
  room_id: string
  user_id: string
  username: string
  content: string
  created_at: string
}

export interface ChatJoinedEnvelope {
  type: 'joined'
  room_id: string
}

export interface ChatErrorEnvelope {
  type: 'error'
  detail: string
}

export type ServerEnvelope = ChatMessageEnvelope | ChatJoinedEnvelope | ChatErrorEnvelope

export interface User {
  id: string
  username: string
  email: string
  is_bot: boolean
  is_site_admin: boolean
  created_at: string
}

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

export interface Message {
  id: string
  room_id: string
  user_id: string
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

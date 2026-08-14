import { apiFetch } from './client'

export interface PushSubscriptionPayload {
  endpoint: string
  keys: { p256dh: string; auth: string }
}

interface VapidPublicKeyResponse {
  public_key: string | null
}

export function getVapidPublicKey(): Promise<VapidPublicKeyResponse> {
  return apiFetch<VapidPublicKeyResponse>('/api/push/vapid-public-key')
}

export function subscribePush(subscription: PushSubscriptionPayload): Promise<void> {
  return apiFetch<void>('/api/push/subscribe', {
    method: 'POST',
    body: JSON.stringify(subscription),
  })
}

export function unsubscribePush(endpoint: string): Promise<void> {
  return apiFetch<void>('/api/push/subscribe', {
    method: 'DELETE',
    body: JSON.stringify({ endpoint }),
  })
}

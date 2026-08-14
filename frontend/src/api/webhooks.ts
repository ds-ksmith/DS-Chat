import { apiFetch } from './client'
import type {
  EventSubscription,
  EventSubscriptionCreated,
  EventType,
  WebhookIncoming,
} from '../types'

export function createIncomingWebhook(
  roomId: string,
  description?: string,
): Promise<WebhookIncoming> {
  return apiFetch<WebhookIncoming>(`/api/rooms/${roomId}/webhooks/incoming`, {
    method: 'POST',
    body: JSON.stringify({ description: description || null }),
  })
}

export function listIncomingWebhooks(roomId: string): Promise<WebhookIncoming[]> {
  return apiFetch<WebhookIncoming[]>(`/api/rooms/${roomId}/webhooks/incoming`)
}

export function revokeIncomingWebhook(roomId: string, webhookId: string): Promise<void> {
  return apiFetch<void>(`/api/rooms/${roomId}/webhooks/incoming/${webhookId}`, {
    method: 'DELETE',
  })
}

export function createEventSubscription(
  roomId: string,
  eventTypes: EventType[],
  targetUrl: string,
): Promise<EventSubscriptionCreated> {
  return apiFetch<EventSubscriptionCreated>(`/api/rooms/${roomId}/event-subscriptions`, {
    method: 'POST',
    body: JSON.stringify({ event_types: eventTypes, target_url: targetUrl }),
  })
}

export function listEventSubscriptions(roomId: string): Promise<EventSubscription[]> {
  return apiFetch<EventSubscription[]>(`/api/rooms/${roomId}/event-subscriptions`)
}

export function revokeEventSubscription(roomId: string, subscriptionId: string): Promise<void> {
  return apiFetch<void>(`/api/rooms/${roomId}/event-subscriptions/${subscriptionId}`, {
    method: 'DELETE',
  })
}

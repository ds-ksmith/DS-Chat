import { apiFetch } from './client'
import type { ApiScope, ApiToken, ApiTokenCreated, Bot } from '../types'

export function createBot(username: string): Promise<Bot> {
  return apiFetch<Bot>('/api/admin/bots', {
    method: 'POST',
    body: JSON.stringify({ username }),
  })
}

export function listBots(): Promise<Bot[]> {
  return apiFetch<Bot[]>('/api/admin/bots')
}

export function createApiToken(botId: string, scopes: ApiScope[]): Promise<ApiTokenCreated> {
  return apiFetch<ApiTokenCreated>(`/api/admin/bots/${botId}/tokens`, {
    method: 'POST',
    body: JSON.stringify({ scopes }),
  })
}

export function listApiTokens(botId: string): Promise<ApiToken[]> {
  return apiFetch<ApiToken[]>(`/api/admin/bots/${botId}/tokens`)
}

export function revokeApiToken(tokenId: string): Promise<void> {
  return apiFetch<void>(`/api/admin/bots/tokens/${tokenId}`, { method: 'DELETE' })
}

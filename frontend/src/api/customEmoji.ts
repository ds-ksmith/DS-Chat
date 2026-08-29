import { apiFetch, ApiError, NetworkError } from './client'
import type { CustomEmoji } from '../types'

export function listCustomEmoji(): Promise<CustomEmoji[]> {
  return apiFetch<CustomEmoji[]>('/api/custom-emoji')
}

export function getCustomEmojiUrl(shortcode: string): string {
  return `/api/custom-emoji/${encodeURIComponent(shortcode)}/image`
}

export function deleteCustomEmoji(id: string): Promise<void> {
  return apiFetch<void>(`/api/custom-emoji/${id}`, { method: 'DELETE' })
}

// Raw fetch, not apiFetch -- same multipart-boundary reason as
// uploadAvatar/uploadRoomImage (a manually-set Content-Type header would
// omit the boundary the browser generates for FormData).
export async function uploadCustomEmoji(shortcode: string, file: File): Promise<CustomEmoji> {
  const formData = new FormData()
  formData.append('shortcode', shortcode)
  formData.append('file', file)

  let response: Response
  try {
    response = await fetch('/api/custom-emoji', {
      method: 'POST',
      credentials: 'include',
      body: formData,
    })
  } catch {
    throw new NetworkError()
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // response had no JSON body
    }
    throw new ApiError(response.status, detail)
  }

  return (await response.json()) as CustomEmoji
}

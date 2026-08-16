import { apiFetch } from './client'
import type { UploadSettings } from '../types'

export function getUploadLimit(): Promise<UploadSettings> {
  return apiFetch<UploadSettings>('/api/uploads/limit')
}

export function getUserAvatarUrl(userId: string, avatarFilename?: string | null): string {
  return `/api/users/${userId}/avatar${avatarFilename ? `?v=${avatarFilename}` : ''}`
}

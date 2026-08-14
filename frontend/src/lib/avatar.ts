const ACCENT_CYCLE = [
  'var(--accent-cycle-1)',
  'var(--accent-cycle-2)',
  'var(--accent-cycle-3)',
  'var(--accent-cycle-4)',
]

export function initials(name: string): string {
  return name
    .split(' ')
    .filter(Boolean)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

export function accentForIndex(index: number): string {
  return ACCENT_CYCLE[((index % ACCENT_CYCLE.length) + ACCENT_CYCLE.length) % ACCENT_CYCLE.length]
}

export function hashIndex(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) hash = (hash * 31 + str.charCodeAt(i)) | 0
  return Math.abs(hash)
}

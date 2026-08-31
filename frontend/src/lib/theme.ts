import type { CustomThemeColors, TextScale, ThemeName } from '../types'

// The inline custom properties a custom theme sets on :root -- must be
// removed explicitly when switching to a preset, since an inline style
// always wins over :root[data-theme='...']'s stylesheet rule regardless of
// cascade order, so a stale one would otherwise silently override every
// preset picked afterward.
const CUSTOM_THEME_VARS = [
  '--ds-void',
  '--ds-void-2',
  '--ds-surface',
  '--ds-surface-2',
  '--ds-border',
  '--ds-text',
  '--ds-muted',
  '--ds-accent',
  '--ds-accent-2',
  '--ds-accent-3',
  '--ds-highlight',
  '--ds-danger',
  '--card-bg',
]

// Starting point for a user who's never saved a custom palette before --
// exactly tokens.css's default (Dark) values, so "Custom" begins as a copy
// of what they were already looking at rather than something jarring.
export const DEFAULT_CUSTOM_COLORS: CustomThemeColors = {
  void: '#07080f',
  void_2: '#0b0c1a',
  surface: '#101030',
  surface_2: '#181848',
  border: '#242478',
  text: '#fce4fc',
  muted: '#c0ccd8',
  accent: '#60d8fc',
  accent_2: '#6c60fc',
  accent_3: '#7848fc',
  highlight: '#f060fc',
  danger: '#fc6060',
  color_scheme: 'dark',
}

// Applied on load/user-change (AuthContext) and live while editing
// (ProfileModal) -- the single place that knows how to turn either a preset
// name or a custom palette into what's actually on screen.
export function applyTheme(theme: ThemeName | null, customColors: CustomThemeColors | null): void {
  const root = document.documentElement

  if (theme === 'custom' && customColors) {
    root.setAttribute('data-theme', 'custom')
    root.style.setProperty('--ds-void', customColors.void)
    root.style.setProperty('--ds-void-2', customColors.void_2)
    root.style.setProperty('--ds-surface', customColors.surface)
    root.style.setProperty('--ds-surface-2', customColors.surface_2)
    root.style.setProperty('--ds-border', customColors.border)
    root.style.setProperty('--ds-text', customColors.text)
    root.style.setProperty('--ds-muted', customColors.muted)
    root.style.setProperty('--ds-accent', customColors.accent)
    root.style.setProperty('--ds-accent-2', customColors.accent_2)
    root.style.setProperty('--ds-accent-3', customColors.accent_3)
    root.style.setProperty('--ds-highlight', customColors.highlight)
    root.style.setProperty('--ds-danger', customColors.danger)
    // Same two-stop-gradient formula the built-in presets use (see
    // themes.css), just built from the picked surface colors instead of a
    // literal rgba() -- 8-digit hex alpha is well-supported in every
    // evergreen browser and avoids a separate hex-to-rgb conversion.
    root.style.setProperty(
      '--card-bg',
      `linear-gradient(180deg, ${customColors.surface_2}f6, ${customColors.surface}f6)`,
    )
    root.style.setProperty('color-scheme', customColors.color_scheme)
    return
  }

  root.setAttribute('data-theme', theme ?? 'dark')
  for (const varName of CUSTOM_THEME_VARS) root.style.removeProperty(varName)
  root.style.removeProperty('color-scheme')
}

// #71: percentages, not fixed px -- stacks on top of the browser/OS's own
// zoom or accessibility text-size setting instead of overriding it. Every
// component in this app already sizes itself in rem (see tokens.css),
// which is relative to this root value, so setting it here is the one
// change that scales text *and* the message-image/video max-size caps
// (also converted to rem -- see MessageList.css) uniformly, with no
// per-component work.
const TEXT_SCALE_PERCENT: Record<TextScale, string> = {
  small: '87.5%',
  normal: '100%',
  large: '112.5%',
  xlarge: '125%',
}

export function applyTextScale(scale: TextScale | null): void {
  document.documentElement.style.fontSize = TEXT_SCALE_PERCENT[scale ?? 'normal']
}

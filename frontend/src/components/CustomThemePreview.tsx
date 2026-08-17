import type { CustomThemeColors } from '../types'
import './CustomThemePreview.css'

interface CustomThemePreviewProps {
  colors: CustomThemeColors
  highlightedField: keyof CustomThemeColors | null
  onHighlight: (field: keyof CustomThemeColors | null) => void
}

// A miniature, self-contained mockup of the real chat UI, styled entirely
// from inline styles bound to the draft colors -- deliberately not the
// --ds-* custom properties, since those reflect whatever theme is actually
// active right now, not necessarily the one being edited (see
// ProfileModal.tsx's handleEditColorChange comment). Hovering either a
// swatch here or the matching color input elsewhere highlights both, so
// it's clear at a glance which of the 12 fields controls which part of the
// real UI, in both directions.
export function CustomThemePreview({ colors, highlightedField, onHighlight }: CustomThemePreviewProps) {
  function hoverClass(field: keyof CustomThemeColors, extra = ''): string {
    const highlighted = highlightedField === field ? ' ctp-highlighted' : ''
    return `ctp-hoverable${extra ? ` ${extra}` : ''}${highlighted}`
  }

  function hoverHandlers(field: keyof CustomThemeColors) {
    return {
      onMouseEnter: () => onHighlight(field),
      onMouseLeave: () => onHighlight(null),
    }
  }

  return (
    <div
      className={hoverClass('void', 'custom-theme-preview')}
      style={{ background: colors.void }}
      {...hoverHandlers('void')}
    >
      <div className={hoverClass('void_2', 'ctp-sidebar')} style={{ background: colors.void_2 }} {...hoverHandlers('void_2')}>
        <div className={hoverClass('surface', 'ctp-room-row')} style={{ background: colors.surface }} {...hoverHandlers('surface')}>
          <span style={{ color: colors.text }}># general</span>
        </div>
        <div
          className={hoverClass('border', 'ctp-room-row ctp-room-row-quiet')}
          style={{ borderColor: colors.border }}
          {...hoverHandlers('border')}
        >
          <span style={{ color: colors.muted }}># random</span>
        </div>
      </div>
      <div className="ctp-main">
        <div className="ctp-message">
          <div
            className={hoverClass('accent', 'ctp-avatar')}
            style={{ background: colors.accent }}
            {...hoverHandlers('accent')}
          />
          <div className="ctp-message-body">
            <span>
              <span className={hoverClass('accent_2')} style={{ color: colors.accent_2 }} {...hoverHandlers('accent_2')}>
                Alice
              </span>{' '}
              <span className={hoverClass('muted')} style={{ color: colors.muted }} {...hoverHandlers('muted')}>
                2:30 PM
              </span>
            </span>
            <div className={hoverClass('text')} style={{ color: colors.text }} {...hoverHandlers('text')}>
              Hey{' '}
              <span
                className={hoverClass('highlight', 'ctp-mention')}
                style={{ background: `${colors.highlight}30`, color: colors.highlight }}
                {...hoverHandlers('highlight')}
              >
                @bob
              </span>{' '}
              check this out
            </div>
          </div>
          <span
            className={hoverClass('accent_3', 'ctp-badge')}
            style={{ background: colors.accent_3 }}
            {...hoverHandlers('accent_3')}
          >
            Owner
          </span>
        </div>
        <div
          className={hoverClass('surface_2', 'ctp-composer')}
          style={{ background: colors.surface_2, borderColor: colors.border }}
          {...hoverHandlers('surface_2')}
        >
          <span style={{ color: colors.muted }}>Message…</span>
        </div>
        <button
          type="button"
          className={hoverClass('danger', 'ctp-danger-btn')}
          style={{ color: colors.danger, borderColor: colors.danger }}
          {...hoverHandlers('danger')}
        >
          Leave room
        </button>
      </div>
    </div>
  )
}

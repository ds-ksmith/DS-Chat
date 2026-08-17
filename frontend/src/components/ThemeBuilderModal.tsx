import type { CustomThemeColors } from '../types'
import { CustomThemePreview } from './CustomThemePreview'
import './Modal.css'
import './ThemeBuilderModal.css'

interface ColorField {
  key: keyof Omit<CustomThemeColors, 'color_scheme'>
  label: string
}

interface ThemeBuilderModalProps {
  colorFields: ColorField[]
  name: string
  onNameChange: (name: string) => void
  colors: CustomThemeColors
  onColorChange: (key: keyof CustomThemeColors, value: string) => void
  highlightedField: keyof CustomThemeColors | null
  onHighlight: (field: keyof CustomThemeColors | null) => void
  error: string | null
  saving: boolean
  onSave: () => void
  onCancel: () => void
}

// Same editor as ProfileModal.tsx used to render inline, pulled out into its
// own wider dialog (#46) -- the profile modal's .modal is capped at
// min(380px, 100%), which cramped the CustomThemePreview mockup that's
// supposed to make the color-to-UI mapping easy to see. Nested on top of
// ProfileModal rather than replacing it, same stacked-dialog pattern as
// ImageLightbox/FilePreviewModal opening over MessageList.
export function ThemeBuilderModal({
  colorFields,
  name,
  onNameChange,
  colors,
  onColorChange,
  highlightedField,
  onHighlight,
  error,
  saving,
  onSave,
  onCancel,
}: ThemeBuilderModalProps) {
  return (
    <div className="modal-scrim" onClick={onCancel}>
      <div className="modal theme-builder-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Edit theme</h2>
          <button type="button" className="modal-close" onClick={onCancel} aria-label="Close">
            &times;
          </button>
        </div>

        <input
          type="text"
          className="custom-theme-name-input"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="Theme name"
          maxLength={50}
        />

        {/* Full modal width, not sharing a column with the fields below --
            the whole point of this dialog over the old inline editor is
            room for this mockup to read at a legible size. */}
        <CustomThemePreview colors={colors} highlightedField={highlightedField} onHighlight={onHighlight} />

        <div className="theme-builder-lower">
          <div className="custom-theme-grid theme-builder-grid">
            {colorFields.map((field) => (
              <label
                key={field.key}
                className={`custom-theme-field${highlightedField === field.key ? ' custom-theme-field-highlighted' : ''}`}
                onMouseEnter={() => onHighlight(field.key)}
                onMouseLeave={() => onHighlight(null)}
              >
                <input
                  type="color"
                  value={colors[field.key]}
                  onChange={(e) => onColorChange(field.key, e.target.value)}
                  onFocus={() => onHighlight(field.key)}
                  onBlur={() => onHighlight(null)}
                />
                <span>{field.label}</span>
              </label>
            ))}
          </div>

          <div className="custom-theme-scheme">
            <span>Native controls (scrollbars, form inputs)</span>
            <div className="custom-theme-scheme-toggle">
              <button
                type="button"
                className={`btn-secondary${colors.color_scheme === 'light' ? ' custom-theme-scheme-active' : ''}`}
                onClick={() => onColorChange('color_scheme', 'light')}
              >
                Light
              </button>
              <button
                type="button"
                className={`btn-secondary${colors.color_scheme === 'dark' ? ' custom-theme-scheme-active' : ''}`}
                onClick={() => onColorChange('color_scheme', 'dark')}
              >
                Dark
              </button>
            </div>
          </div>
        </div>

        {error && <p className="modal-error">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn-primary" onClick={onSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

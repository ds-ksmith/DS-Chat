import type { ReactNode } from 'react'
import type { FormatAction, InlineMarker } from '../lib/markdownFormat'
import './FormattingToolbar.css'

interface FormattingToolbarProps {
  id: string
  disabled?: boolean
  onAction: (action: FormatAction) => void
}

interface ToolbarButton {
  label: string
  // Shows the syntax the button inserts -- the toolbar doubles as the
  // "quick guide" for people who'd rather learn to type it themselves.
  title: string
  content: ReactNode
  action: FormatAction
}

const inline = (marker: InlineMarker): FormatAction => ({ kind: 'inline', marker })

const GROUPS: ToolbarButton[][] = [
  [
    { label: 'Bold', title: 'Bold: **text**', content: <b>B</b>, action: inline('**') },
    { label: 'Italic', title: 'Italic: *text*', content: <i>I</i>, action: inline('*') },
    { label: 'Strikethrough', title: 'Strikethrough: ~~text~~', content: <s>S</s>, action: inline('~~') },
  ],
  [
    { label: 'Inline code', title: 'Inline code: `code`', content: '</>', action: inline('`') },
    { label: 'Code block', title: 'Code block: ``` on its own lines', content: '{ }', action: { kind: 'codeBlock' } },
  ],
  [
    {
      label: 'Link',
      title: 'Link: [text](url)',
      content: (
        <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path
            d="M8.5 11.5a3 3 0 0 0 4.2 0l2.6-2.6a3 3 0 0 0-4.2-4.2l-.9.9M11.5 8.5a3 3 0 0 0-4.2 0l-2.6 2.6a3 3 0 0 0 4.2 4.2l.9-.9"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ),
      action: { kind: 'link' },
    },
    { label: 'Quote', title: 'Quote: > text', content: '“', action: { kind: 'prefix', prefix: 'quote' } },
  ],
  [
    { label: 'Bulleted list', title: 'Bulleted list: - item', content: '•', action: { kind: 'prefix', prefix: 'bullet' } },
    { label: 'Numbered list', title: 'Numbered list: 1. item', content: '1.', action: { kind: 'prefix', prefix: 'ordered' } },
  ],
  [
    { label: 'Heading 1', title: 'Heading 1: # text', content: 'H1', action: { kind: 'heading', level: 1 } },
    { label: 'Heading 2', title: 'Heading 2: ## text', content: 'H2', action: { kind: 'heading', level: 2 } },
    { label: 'Heading 3', title: 'Heading 3: ### text', content: 'H3', action: { kind: 'heading', level: 3 } },
  ],
  [
    { label: 'Subscript', title: 'Subscript: ~text~ (no spaces)', content: 'x₂', action: inline('~') },
    { label: 'Superscript', title: 'Superscript: ^text^ (no spaces)', content: 'x²', action: inline('^') },
  ],
]

export function FormattingToolbar({ id, disabled, onAction }: FormattingToolbarProps) {
  return (
    <div id={id} className="formatting-toolbar" role="toolbar" aria-label="Formatting">
      {GROUPS.map((group) => (
        <div key={group[0].label} className="formatting-toolbar-group">
          {group.map((button) => (
            <button
              key={button.label}
              type="button"
              className="formatting-toolbar-btn"
              title={button.title}
              aria-label={button.label}
              disabled={disabled}
              // Keeps focus (and the selection) in the textarea -- a click
              // on a button would otherwise blur it, and on mobile dismiss
              // the keyboard.
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => onAction(button.action)}
            >
              {button.content}
            </button>
          ))}
        </div>
      ))}
      {/* A new tab on purpose: the draft lives in Composer's own state, so
          navigating this one away would lose it. */}
      <a
        className="formatting-toolbar-btn formatting-toolbar-help"
        href="/help#formatting"
        target="_blank"
        rel="noopener noreferrer"
        title="Formatting help (opens in a new tab)"
        aria-label="Formatting help"
      >
        ?
      </a>
    </div>
  )
}

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { FormatAction } from '../lib/markdownFormat'
import { FormattingToolbar } from './FormattingToolbar'

afterEach(cleanup)

const EXPECTED: [string, FormatAction][] = [
  ['Bold', { kind: 'inline', marker: '**' }],
  ['Italic', { kind: 'inline', marker: '*' }],
  ['Strikethrough', { kind: 'inline', marker: '~~' }],
  ['Inline code', { kind: 'inline', marker: '`' }],
  ['Code block', { kind: 'codeBlock' }],
  ['Link', { kind: 'link' }],
  ['Quote', { kind: 'prefix', prefix: 'quote' }],
  ['Bulleted list', { kind: 'prefix', prefix: 'bullet' }],
  ['Numbered list', { kind: 'prefix', prefix: 'ordered' }],
  ['Heading 1', { kind: 'heading', level: 1 }],
  ['Heading 2', { kind: 'heading', level: 2 }],
  ['Heading 3', { kind: 'heading', level: 3 }],
  ['Subscript', { kind: 'inline', marker: '~' }],
  ['Superscript', { kind: 'inline', marker: '^' }],
]

describe('FormattingToolbar', () => {
  it.each(EXPECTED)('%s button calls onAction with its action', (label, action) => {
    const onAction = vi.fn()
    render(<FormattingToolbar id="t" onAction={onAction} />)
    fireEvent.click(screen.getByRole('button', { name: label }))
    expect(onAction).toHaveBeenCalledTimes(1)
    expect(onAction).toHaveBeenCalledWith(action)
  })

  it('disables every button when disabled, but leaves the help link usable', () => {
    render(<FormattingToolbar id="t" disabled onAction={vi.fn()} />)
    const buttons = screen.getAllByRole('button') as HTMLButtonElement[]
    expect(buttons).toHaveLength(EXPECTED.length)
    expect(buttons.every((b) => b.disabled)).toBe(true)
    expect(screen.getByRole('link', { name: 'Formatting help' })).toBeTruthy()
  })

  it('opens help in a new tab so the draft in the composer is not lost', () => {
    render(<FormattingToolbar id="t" onAction={vi.fn()} />)
    const help = screen.getByRole('link', { name: 'Formatting help' })
    expect(help.getAttribute('href')).toBe('/help#formatting')
    expect(help.getAttribute('target')).toBe('_blank')
    expect(help.getAttribute('rel')).toContain('noopener')
  })

  it('keeps focus in the textarea by cancelling mousedown on buttons', () => {
    render(<FormattingToolbar id="t" onAction={vi.fn()} />)
    // fireEvent returns false when the event's default was prevented.
    expect(fireEvent.mouseDown(screen.getByRole('button', { name: 'Bold' }))).toBe(false)
  })
})

import { describe, expect, it } from 'vitest'
import { applyFormat, type FormatAction, type InlineMarker, type TextState } from './markdownFormat'

// ⟦ and ⟧ mark the selection, so cases read as plain strings -- an empty
// pair (⟦⟧) is a bare cursor.
const L = '⟦'
const R = '⟧'

function parse(s: string): TextState {
  const start = s.indexOf(L)
  const end = s.indexOf(R) - 1
  return { value: s.replace(L, '').replace(R, ''), start, end }
}

function render({ value, start, end }: TextState): string {
  return value.slice(0, start) + L + value.slice(start, end) + R + value.slice(end)
}

function fmt(s: string, action: FormatAction): string {
  return render(applyFormat(parse(s), action))
}

const inline = (marker: InlineMarker): FormatAction => ({ kind: 'inline', marker })

describe('inline wrap', () => {
  it('wraps the selection and keeps the inner text selected', () => {
    expect(fmt('say ⟦hi⟧ now', inline('**'))).toBe('say **⟦hi⟧** now')
  })

  it('inserts an empty pair with the cursor between when nothing is selected', () => {
    expect(fmt('say ⟦⟧now', inline('**'))).toBe('say **⟦⟧**now')
  })

  it('unwraps when the markers sit just outside the selection', () => {
    expect(fmt('say **⟦hi⟧** now', inline('**'))).toBe('say ⟦hi⟧ now')
  })

  it('unwraps when the selection includes the markers', () => {
    expect(fmt('say ⟦**hi**⟧ now', inline('**'))).toBe('say ⟦hi⟧ now')
  })

  it('keeps markers outside leading/trailing whitespace in the selection', () => {
    expect(fmt('a⟦ hi ⟧b', inline('**'))).toBe('a **⟦hi⟧** b')
  })

  it('italic on a bold selection adds italic rather than stripping bold', () => {
    expect(fmt('x **⟦hi⟧** y', inline('*'))).toBe('x ***⟦hi⟧*** y')
  })

  it('removes just bold from bold+italic', () => {
    expect(fmt('x ***⟦hi⟧*** y', inline('**'))).toBe('x *⟦hi⟧* y')
  })

  it('removes just italic from bold+italic', () => {
    expect(fmt('x ***⟦hi⟧*** y', inline('*'))).toBe('x **⟦hi⟧** y')
  })

  it('strikethrough toggles off without being confused by subscript', () => {
    expect(fmt('x ~~⟦hi⟧~~ y', inline('~~'))).toBe('x ⟦hi⟧ y')
    expect(fmt('a ⟦hi⟧ b', inline('~'))).toBe('a ~⟦hi⟧~ b')
  })

  it('handles inline code and superscript', () => {
    expect(fmt('run ⟦ls⟧', inline('`'))).toBe('run `⟦ls⟧`')
    expect(fmt('x⟦2⟧', inline('^'))).toBe('x^⟦2⟧^')
  })

  it.each(['**', '*', '~~', '~', '`', '^'] as InlineMarker[])('%s: applying twice restores the original', (marker) => {
    const original = parse('a ⟦b⟧ c')
    const once = applyFormat(original, inline(marker))
    expect(once.value).not.toBe(original.value)
    expect(applyFormat(once, inline(marker))).toEqual(original)
  })
})

describe('line prefixes', () => {
  it('prefixes the current line and moves the cursor with it', () => {
    expect(fmt('hello⟦⟧', { kind: 'prefix', prefix: 'quote' })).toBe('> hello⟦⟧')
    expect(fmt('one\ntw⟦⟧o', { kind: 'prefix', prefix: 'quote' })).toBe('one\n> tw⟦⟧o')
  })

  it('starts a list on a blank line', () => {
    expect(fmt('⟦⟧', { kind: 'prefix', prefix: 'bullet' })).toBe('- ⟦⟧')
  })

  it('prefixes every selected line, then toggles them back off', () => {
    const bullet: FormatAction = { kind: 'prefix', prefix: 'bullet' }
    expect(fmt('⟦a\nb⟧', bullet)).toBe('⟦- a\n- b⟧')
    expect(fmt('⟦- a\n- b⟧', bullet)).toBe('⟦a\nb⟧')
  })

  it('numbers lines sequentially, skipping blank lines, and renumbers existing numbers', () => {
    const ordered: FormatAction = { kind: 'prefix', prefix: 'ordered' }
    expect(fmt('⟦a\n\nb⟧', ordered)).toBe('⟦1. a\n\n2. b⟧')
    expect(fmt('⟦1. a\nb⟧', ordered)).toBe('⟦1. a\n2. b⟧')
    expect(fmt('⟦1. a\n2. b⟧', ordered)).toBe('⟦a\nb⟧')
  })

  it('does not include a line the selection only touches at its very start', () => {
    expect(fmt('a\n⟦b\n⟧c', { kind: 'prefix', prefix: 'bullet' })).toBe('a\n⟦- b⟧\nc')
  })
})

describe('headings', () => {
  it('adds, replaces, and toggles off the heading level', () => {
    expect(fmt('title⟦⟧', { kind: 'heading', level: 2 })).toBe('## title⟦⟧')
    expect(fmt('⟦# hi⟧', { kind: 'heading', level: 2 })).toBe('⟦## hi⟧')
    expect(fmt('⟦## hi⟧', { kind: 'heading', level: 1 })).toBe('⟦# hi⟧')
    expect(fmt('⟦## hi⟧', { kind: 'heading', level: 2 })).toBe('⟦hi⟧')
  })
})

describe('code block', () => {
  it('inserts an empty fenced block with the cursor on the blank line', () => {
    expect(fmt('⟦⟧', { kind: 'codeBlock' })).toBe('```\n⟦⟧\n```')
  })

  it('puts the fences on their own lines when the selection is mid-line', () => {
    expect(fmt('see ⟦x = 1⟧ here', { kind: 'codeBlock' })).toBe('see \n```\n⟦x = 1⟧\n```\n here')
  })

  it('does not double the newline when the selection already ends with one', () => {
    expect(fmt('⟦a\n⟧b', { kind: 'codeBlock' })).toBe('```\n⟦a⟧\n```\nb')
  })
})

describe('link', () => {
  it('wraps the selection and selects the placeholder url', () => {
    expect(fmt('see ⟦docs⟧', { kind: 'link' })).toBe('see [docs](⟦url⟧)')
  })

  it('treats a selected url as the target and leaves the cursor in the text brackets', () => {
    expect(fmt('⟦https://example.com⟧', { kind: 'link' })).toBe('[⟦⟧](https://example.com)')
  })

  it('inserts a placeholder link with its text selected when nothing is selected', () => {
    expect(fmt('a ⟦⟧', { kind: 'link' })).toBe('a [⟦link text⟧](url)')
  })
})

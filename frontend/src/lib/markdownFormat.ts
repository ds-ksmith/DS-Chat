// #75: pure text transforms behind the composer's formatting toolbar. Each
// takes the textarea's value plus its selection and returns the same shape,
// so Composer just applies the result -- keeping this free of React/DOM is
// what makes the fiddly selection math directly unit-testable.
export interface TextState {
  value: string
  start: number
  end: number
}

export type InlineMarker = '**' | '*' | '~~' | '`' | '~' | '^'

export type FormatAction =
  | { kind: 'inline'; marker: InlineMarker }
  | { kind: 'prefix'; prefix: 'quote' | 'bullet' | 'ordered' }
  | { kind: 'heading'; level: 1 | 2 | 3 }
  | { kind: 'codeBlock' }
  | { kind: 'link' }

// Markers whose doubled form is a *different* format (`**` bold vs `*`
// italic, `~~` strikethrough vs `~` subscript), so "is this already
// wrapped?" has to look at how long the run of marker characters is rather
// than just whether one is present.
const DOUBLED_IS_DIFFERENT = new Set(['*', '~'])

// A run of 3 `*` is bold+italic: bold (2) and italic (1) are both "present".
function hasMarker(marker: string, run: number): boolean {
  if (marker.length === 2) return run >= 2
  return DOUBLED_IS_DIFFERENT.has(marker[0]) ? run % 2 === 1 : run >= 1
}

function applyInline(state: TextState, marker: InlineMarker): TextState {
  const { value, start, end } = state
  const ch = marker[0]
  const m = marker.length
  const sel = value.slice(start, end)

  // Selection includes the markers themselves (e.g. the user selected the
  // whole `**word**`) -- unwrap inside the selection.
  if (sel.length > 0) {
    let lead = 0
    while (lead < sel.length && sel[lead] === ch) lead++
    let trail = 0
    while (trail < sel.length - lead && sel[sel.length - 1 - trail] === ch) trail++
    const run = Math.min(lead, trail)
    if (run > 0 && hasMarker(marker, run) && sel.length > 2 * m) {
      const inner = sel.slice(m, sel.length - m)
      return { value: value.slice(0, start) + inner + value.slice(end), start, end: start + inner.length }
    }
  }

  // Markers sit just outside the selection. Skipped when the selection has
  // edge whitespace: markers adjacent to it belong to neighbouring spans
  // (`*a* and *b*` with " and " selected), not to this selection.
  const edgeWhitespace = sel.length > 0 && (/^\s/.test(sel) || /\s$/.test(sel))
  if (!edgeWhitespace) {
    let before = 0
    while (start - before - 1 >= 0 && value[start - before - 1] === ch) before++
    let after = 0
    while (end + after < value.length && value[end + after] === ch) after++
    const run = Math.min(before, after)
    if (run > 0 && hasMarker(marker, run)) {
      return {
        value: value.slice(0, start - m) + sel + value.slice(end + m),
        start: start - m,
        end: end - m,
      }
    }
  }

  // Nothing selected (or only whitespace): drop in an empty pair, cursor between.
  if (sel.trim() === '') {
    return {
      value: value.slice(0, start) + marker + marker + value.slice(start),
      start: start + m,
      end: start + m,
    }
  }

  // Markdown doesn't treat `** word**` as bold -- keep the markers hugging
  // the text, outside any whitespace the selection happens to include.
  const innerStart = start + (sel.length - sel.trimStart().length)
  const innerEnd = end - (sel.length - sel.trimEnd().length)
  return {
    value:
      value.slice(0, innerStart) + marker + value.slice(innerStart, innerEnd) + marker + value.slice(innerEnd),
    start: innerStart + m,
    end: innerEnd + m,
  }
}

// The whole lines a selection touches. A selection that ends right after a
// newline (i.e. at the very start of the next line) doesn't count that line.
function lineBounds(value: string, start: number, end: number) {
  const lineStart = start === 0 ? 0 : value.lastIndexOf('\n', start - 1) + 1
  const effectiveEnd = end > start && value[end - 1] === '\n' ? end - 1 : end
  const nextNewline = value.indexOf('\n', effectiveEnd)
  return { lineStart, lineEnd: nextNewline === -1 ? value.length : nextNewline }
}

function transformLines(state: TextState, transform: (lines: string[]) => string[]): TextState {
  const { value, start, end } = state
  const { lineStart, lineEnd } = lineBounds(value, start, end)
  const oldBlock = value.slice(lineStart, lineEnd)
  const newBlock = transform(oldBlock.split('\n')).join('\n')
  const next = value.slice(0, lineStart) + newBlock + value.slice(lineEnd)
  if (start === end) {
    const cursor = Math.max(lineStart, start + (newBlock.length - oldBlock.length))
    return { value: next, start: cursor, end: cursor }
  }
  // Keep the affected lines selected so the same button toggles it back off.
  return { value: next, start: lineStart, end: lineStart + newBlock.length }
}

const ORDERED_RE = /^\d+\. /

function applyPrefix(state: TextState, kind: 'quote' | 'bullet' | 'ordered'): TextState {
  const marker = kind === 'quote' ? '> ' : '- '
  const has = (line: string) => (kind === 'ordered' ? ORDERED_RE.test(line) : line.startsWith(marker))
  const strip = (line: string) => (kind === 'ordered' ? line.replace(ORDERED_RE, '') : line.slice(marker.length))

  return transformLines(state, (lines) => {
    // Blank lines inside a multi-line selection are paragraph breaks, not
    // list items -- only a lone blank line (cursor on an empty line) gets one.
    const multi = lines.length > 1
    const skip = (line: string) => multi && line === ''
    const targets = lines.filter((line) => !skip(line))
    if (targets.length > 0 && targets.every(has)) {
      return lines.map((line) => (has(line) ? strip(line) : line))
    }
    let n = 0
    return lines.map((line) => {
      if (skip(line)) return line
      n++
      if (kind === 'ordered') return `${n}. ${strip(line)}`
      return has(line) ? line : marker + line
    })
  })
}

const HEADING_RE = /^#{1,6} /

function applyHeading(state: TextState, level: 1 | 2 | 3): TextState {
  const prefix = '#'.repeat(level) + ' '
  return transformLines(state, (lines) => {
    const multi = lines.length > 1
    const skip = (line: string) => multi && line === ''
    const targets = lines.filter((line) => !skip(line))
    if (targets.length > 0 && targets.every((line) => line.startsWith(prefix))) {
      return lines.map((line) => (line.startsWith(prefix) ? line.slice(prefix.length) : line))
    }
    return lines.map((line) => (skip(line) ? line : prefix + line.replace(HEADING_RE, '')))
  })
}

// A fence only counts at the start of a line, so mid-line cursors get a
// newline inserted first.
function applyCodeBlock(state: TextState): TextState {
  const { value, start, end } = state
  const before = value.slice(0, start)
  const after = value.slice(end)
  const sel = value.slice(start, end).replace(/\n$/, '')
  const lead = before.length > 0 && !before.endsWith('\n') ? '\n' : ''
  const trail = after.length > 0 && !after.startsWith('\n') ? '\n' : ''
  const next = `${before}${lead}\`\`\`\n${sel}\n\`\`\`${trail}${after}`
  const innerStart = before.length + lead.length + 4
  return { value: next, start: innerStart, end: innerStart + sel.length }
}

function applyLink(state: TextState): TextState {
  const { value, start, end } = state
  const sel = value.slice(start, end)
  let text: string
  let selStart: number
  let selEnd: number
  if (/^https?:\/\/\S+$/.test(sel)) {
    text = `[](${sel})`
    selStart = selEnd = start + 1
  } else if (sel) {
    text = `[${sel}](url)`
    selStart = start + sel.length + 3
    selEnd = selStart + 3
  } else {
    text = '[link text](url)'
    selStart = start + 1
    selEnd = selStart + 9
  }
  return { value: value.slice(0, start) + text + value.slice(end), start: selStart, end: selEnd }
}

export function applyFormat(state: TextState, action: FormatAction): TextState {
  switch (action.kind) {
    case 'inline':
      return applyInline(state, action.marker)
    case 'prefix':
      return applyPrefix(state, action.prefix)
    case 'heading':
      return applyHeading(state, action.level)
    case 'codeBlock':
      return applyCodeBlock(state)
    case 'link':
      return applyLink(state)
  }
}

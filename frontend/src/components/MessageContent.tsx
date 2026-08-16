import Markdown from 'markdown-to-jsx'
import { EMOJI_SHORTCODES } from '../lib/emojiShortcodes'

interface MessageContentProps {
  content: string
}

interface MarkdownImageLinkProps {
  src?: string
  alt?: string
  title?: string
}

// Markdown image embeds (`![alt](url)`) degrade to a link instead of an
// <img> -- the app already has a first-class image-attachment upload
// (MessageImage), and a second, unmoderated remote-image path would both
// duplicate that and leak the viewer's IP/UA to arbitrary URLs.
function MarkdownImageLink({ src, alt, title }: MarkdownImageLinkProps) {
  if (!src) return null
  return (
    <a href={src} target="_blank" rel="noopener noreferrer" title={title}>
      {alt || src}
    </a>
  )
}

const SHORTCODE_PATTERN = /:([a-z0-9_+-]+):/g

// Converts a complete `:name:` shortcode to its emoji, skipping fenced code
// blocks and inline code spans -- someone pasting code containing
// `:something:` (a Ruby symbol, a dict key) shouldn't get it silently
// turned into an emoji. This is render-time only: stored/sent content
// always keeps the literal `:name:` text, matching how markdown itself is
// never converted until display.
function convertShortcodes(text: string): string {
  const lines = text.split('\n')
  let inFence = false
  return lines
    .map((line) => {
      if (/^\s*```/.test(line)) {
        inFence = !inFence
        return line
      }
      if (inFence) return line
      // Splitting on backtick-delimited spans keeps inline code (`:foo:`)
      // untouched -- odd-indexed segments are the code spans themselves.
      return line
        .split(/(`+[^`]*`+)/g)
        .map((part, i) =>
          i % 2 === 0
            ? part.replace(SHORTCODE_PATTERN, (match, name) => EMOJI_SHORTCODES[name] ?? match)
            : part,
        )
        .join('')
    })
    .join('\n')
}

// CommonMark treats a single newline as a soft break (rendered as a space),
// not a visible line break -- only a trailing double-space or blank line
// produces one. The Composer's Shift+Enter has always inserted a plain
// newline expecting a visible line break, so without this, existing
// multi-line messages would silently collapse onto one line once markdown
// parsing is introduced. This restores that behavior by appending a hard-
// break marker to single newlines, while leaving fenced code blocks (where
// trailing whitespace shouldn't be added) and blank-line paragraph breaks
// untouched.
function preserveLineBreaks(text: string): string {
  const lines = text.split('\n')
  let inFence = false
  return lines
    .map((line, i) => {
      if (/^\s*```/.test(line)) inFence = !inFence
      const isLast = i === lines.length - 1
      const nextIsBlank = !isLast && lines[i + 1] === ''
      if (inFence || isLast || nextIsBlank || line === '') return line
      return line + '  '
    })
    .join('\n')
}

// Shared with FilePreviewModal so both render paths carry the exact same
// XSS mitigation (disableParsingRawHTML) -- duplicating this object would
// risk the two drifting out of sync if one gets edited later.
export const MARKDOWN_OPTIONS = {
  // The core XSS mitigation: raw HTML in message content is escaped
  // and printed literally instead of being parsed into elements.
  disableParsingRawHTML: true,
  overrides: {
    a: { props: { target: '_blank', rel: 'noopener noreferrer' } },
    img: { component: MarkdownImageLink },
  },
}

export function MessageContent({ content }: MessageContentProps) {
  return <Markdown options={MARKDOWN_OPTIONS}>{preserveLineBreaks(convertShortcodes(content))}</Markdown>
}

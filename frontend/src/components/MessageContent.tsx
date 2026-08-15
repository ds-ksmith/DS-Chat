import Markdown from 'markdown-to-jsx'

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

export function MessageContent({ content }: MessageContentProps) {
  return (
    <Markdown
      options={{
        // The core XSS mitigation: raw HTML in message content is escaped
        // and printed literally instead of being parsed into elements.
        disableParsingRawHTML: true,
        overrides: {
          a: { props: { target: '_blank', rel: 'noopener noreferrer' } },
          img: { component: MarkdownImageLink },
        },
      }}
    >
      {preserveLineBreaks(content)}
    </Markdown>
  )
}

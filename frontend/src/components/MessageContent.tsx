import Markdown from 'markdown-to-jsx'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { EMOJI_SHORTCODES } from '../lib/emojiShortcodes'

interface MessageContentProps {
  content: string
  // Validated against actual room members so a bare '@' in prose can't
  // false-positive -- optional since FilePreviewModal reuses this same
  // component for markdown file previews, where "@mentioning a person"
  // doesn't apply.
  memberUsernames?: Set<string>
  // #47: room-name -> id, scoped to rooms the *viewer* belongs to (not the
  // sender, and not every site room) -- resolving purely against the
  // viewer's own room list means a reference to a private room the viewer
  // isn't in quietly renders as plain text instead of a link, the same way
  // an @mention of someone outside the room does. Optional for the same
  // reason memberUsernames is (FilePreviewModal reuse).
  myRooms?: Map<string, string>
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

interface MarkdownLinkProps {
  href?: string
  children?: ReactNode
}

// highlightMentions (below) turns a validated @username into a
// `[@username](mention:username)` link so markdown-to-jsx parses it as a
// normal link node -- this override is what turns that back into a styled
// span instead of an actual anchor. highlightRoomReferences does the same
// trick for #roomname, but a room reference *is* meant to be navigable, so
// it becomes a real (client-side-routed) Link instead of an inert span.
// Everything else renders as a real external link, same as before mentions
// existed.
function MarkdownLink({ href, children }: MarkdownLinkProps) {
  if (href?.startsWith('mention:')) {
    return <span className="message-mention">{children}</span>
  }
  if (href?.startsWith('room:')) {
    return (
      <Link to={`/rooms/${href.slice('room:'.length)}`} className="message-room-reference">
        {children}
      </Link>
    )
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
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

const MENTION_PATTERN = /@([a-zA-Z0-9_.-]+)/g

// Turns a validated @username into `[@username](mention:username)` --
// markdown-to-jsx parses that as an ordinary link node, which the `a`
// override above then renders as a styled span instead of an anchor. Skips
// fenced code blocks and inline code spans, same convention (and same
// reasoning) as convertShortcodes above -- pasted code containing a bare
// '@' shouldn't light up as if someone were paged. Kept in sync with
// backend/app/services/mention_service.py's equivalent server-side skip
// logic, which decides who actually gets notified.
function highlightMentions(text: string, memberUsernames: Set<string>): string {
  if (memberUsernames.size === 0) return text
  const lines = text.split('\n')
  let inFence = false
  return lines
    .map((line) => {
      if (/^\s*```/.test(line)) {
        inFence = !inFence
        return line
      }
      if (inFence) return line
      return line
        .split(/(`+[^`]*`+)/g)
        .map((part, i) =>
          i % 2 === 0
            ? part.replace(MENTION_PATTERN, (match, username) =>
                memberUsernames.has(username) ? `[${match}](mention:${username})` : match,
              )
            : part,
        )
        .join('')
    })
    .join('\n')
}

const ROOM_REFERENCE_PATTERN = /#([a-zA-Z0-9_.-]+)/g

// Same trick as highlightMentions, targeting #roomname instead of
// @username -- turns a validated reference into `[#roomname](room:id)` so
// the `a` override above renders it as a real link. Kept in sync with
// backend/app/services/room_reference_service.py's matching pattern (which
// decides what actually gets stored server-side; this is purely a display-
// time lookup against rooms the viewer already knows about).
function highlightRoomReferences(text: string, myRooms: Map<string, string>): string {
  if (myRooms.size === 0) return text
  const lines = text.split('\n')
  let inFence = false
  return lines
    .map((line) => {
      if (/^\s*```/.test(line)) {
        inFence = !inFence
        return line
      }
      if (inFence) return line
      return line
        .split(/(`+[^`]*`+)/g)
        .map((part, i) =>
          i % 2 === 0
            ? part.replace(ROOM_REFERENCE_PATTERN, (match, roomName) => {
                const roomId = myRooms.get(roomName)
                return roomId ? `[${match}](room:${roomId})` : match
              })
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
    a: { component: MarkdownLink },
    img: { component: MarkdownImageLink },
  },
}

export function MessageContent({ content, memberUsernames, myRooms }: MessageContentProps) {
  const withMentions = memberUsernames ? highlightMentions(content, memberUsernames) : content
  const withRoomRefs = myRooms ? highlightRoomReferences(withMentions, myRooms) : withMentions
  return <Markdown options={MARKDOWN_OPTIONS}>{preserveLineBreaks(convertShortcodes(withRoomRefs))}</Markdown>
}

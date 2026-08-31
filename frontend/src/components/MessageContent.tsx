import Markdown from 'markdown-to-jsx'
import type { CSSProperties, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { getCustomEmojiUrl } from '../api/customEmoji'
import { useAuth } from '../context/AuthContext'
import { useCustomEmoji } from '../context/CustomEmojiContext'
import { EMOJI_SHORTCODES } from '../lib/emojiShortcodes'
import './MessageContent.css'

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
// convertSubSuperscript (#21) reuses the identical trick for `~sub~`/`^sup^`
// -- markdown-to-jsx has no plugin hook for new inline syntax, but a link is
// something it already parses correctly, so `sub:`/`sup:` "URLs" are just
// another carrier for meaning the parser was never told about. Everything
// else renders as a real external link, same as before mentions existed.
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
  if (href === 'sub:') {
    return <sub>{children}</sub>
  }
  if (href === 'sup:') {
    return <sup>{children}</sup>
  }
  if (href?.startsWith('emoji:')) {
    const shortcode = href.slice('emoji:'.length)
    return (
      <img
        src={getCustomEmojiUrl(shortcode)}
        alt={`:${shortcode}:`}
        title={`:${shortcode}:`}
        className="message-custom-emoji"
      />
    )
  }
  // #71: a raw unicode emoji has no element of its own to size independently
  // of the surrounding text -- it's just characters in a string. Wrapping
  // each one individually (see wrapEmojiGlyphs below) gives it one, purely
  // so the emoji-size preference can scale it via CSS the same way it
  // already scales a custom emoji's <img>.
  if (href === 'glyph:') {
    return <span className="inline-emoji">{children}</span>
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

// #21: single tilde/caret delimiters, no spaces inside, and not doubled --
// `~~text~~` is strikethrough (already natively supported) so a leading or
// trailing extra `~` excludes the match, matching markdownguide.org's
// extended syntax for both constructs. Converts a complete `~sub~`/`^sup^`
// span to `[sub](sub:)`/`[sup](sup:)` -- see MarkdownLink's comment for why
// a link is the carrier.
const SUBSCRIPT_PATTERN = /(?<!~)~([^~\s]+)~(?!~)/g
const SUPERSCRIPT_PATTERN = /\^([^^\s]+)\^/g

function convertSubSuperscript(text: string): string {
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
            ? part
                .replace(SUBSCRIPT_PATTERN, (_match, inner: string) => `[${inner}](sub:)`)
                .replace(SUPERSCRIPT_PATTERN, (_match, inner: string) => `[${inner}](sup:)`)
            : part,
        )
        .join('')
    })
    .join('\n')
}

// #21: markdown-to-jsx has no option for an explicit heading anchor --
// every heading already gets an auto-generated slug from its own text
// (useful for linking within a message), and `{#custom-id}` is meant to
// *override* that slug, not add a second id next to it. There's no plugin
// hook for new block syntax either, so this strips the marker from the
// heading's own text (same fence-skipping convention as the functions
// above) and remembers the association by that now-bare text -- the one
// hook markdown-to-jsx *does* expose, `slugify` (see createMarkdownOptions
// below), gets called with exactly that text, letting the requested id
// stand in for the auto-generated one.
const HEADING_ID_PATTERN = /^(#{1,6}\s+.*?)\s*\{#([a-zA-Z0-9_-]+)\}\s*$/

function extractHeadingIds(text: string): { text: string; headingIds: Map<string, string> } {
  const headingIds = new Map<string, string>()
  const lines = text.split('\n')
  let inFence = false
  const nextLines = lines.map((line) => {
    if (/^\s*```/.test(line)) {
      inFence = !inFence
      return line
    }
    if (inFence) return line
    const match = line.match(HEADING_ID_PATTERN)
    if (!match) return line
    const [, headingLine, customId] = match
    headingIds.set(headingLine.replace(/^#{1,6}\s+/, ''), customId)
    return headingLine
  })
  return { text: nextLines.join('\n'), headingIds }
}

// #18: a *complete* `:name:` that survived convertShortcodes above (it only
// replaces names it recognizes, so an unmatched one -- built-in or not --
// passes through untouched) and matches a shortcode this install actually
// has a custom emoji for. Turns it into `[​:name:​](emoji:name)`, the same
// link-trick MarkdownLink's other branches use -- deliberately reusing the
// exact fence/code-span-skip convention every other converter in this file
// follows, for the same reason (a pasted `:some_key:` in code shouldn't
// light up as an emoji any more than an unrelated one should).
const CUSTOM_EMOJI_PATTERN = /:([a-z0-9_-]+):/g

function convertCustomEmojiShortcodes(text: string, shortcodes: Set<string>): string {
  if (shortcodes.size === 0) return text
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
            ? part.replace(CUSTOM_EMOJI_PATTERN, (match, name) =>
                shortcodes.has(name) ? `[${match}](emoji:${name})` : match,
              )
            : part,
        )
        .join('')
    })
    .join('\n')
}

// Reaction pills and the "recently used" emoji row don't go through the
// markdown pipeline at all -- they render a single stored value directly.
// A custom emoji's value there is its literal `:shortcode:` (see
// backend's MessageReaction.emoji); this is the equivalent one-value
// resolution for those spots, so a deleted-since-reacted-with custom
// emoji degrades to plain `:shortcode:` text instead of a broken image.
interface EmojiGlyphProps {
  value: string
}

export function EmojiGlyph({ value }: EmojiGlyphProps) {
  const { byShortcode } = useCustomEmoji()
  const match = /^:([a-z0-9_-]+):$/.exec(value)
  const shortcode = match?.[1]
  if (shortcode && byShortcode.has(shortcode)) {
    return (
      <img
        src={getCustomEmojiUrl(shortcode)}
        alt={value}
        title={value}
        className="message-custom-emoji"
      />
    )
  }
  // Wrapped the same way wrapEmojiGlyphs wraps a raw emoji in message text
  // (see .inline-emoji), so a --emoji-scale set on an ancestor (the
  // reaction pill's own span in MessageList.tsx) scales this the same way
  // it scales the .message-custom-emoji img above -- and falls back to a
  // no-op 1x everywhere else (the picker) with no --emoji-scale set at all.
  return <span className="inline-emoji">{value}</span>
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
// XSS mitigation (disableParsingRawHTML) and #21's heading-id/sub/superscript
// support -- duplicating this would risk the two drifting out of sync if
// one gets edited later. A function, not a plain constant, since `slugify`
// needs each render's own headingIds map (see extractHeadingIds above) --
// there's no per-render state to close over in a module-level object.
export function createMarkdownOptions(headingIds: Map<string, string>) {
  return {
    // The core XSS mitigation: raw HTML in message content is escaped
    // and printed literally instead of being parsed into elements.
    disableParsingRawHTML: true,
    overrides: {
      a: { component: MarkdownLink },
      img: { component: MarkdownImageLink },
    },
    slugify: (input: string, defaultFn: (input: string) => string) =>
      headingIds.get(input) ?? defaultFn(input),
  }
}

// #21: preprocessing shared by MessageContent and FilePreviewModal --
// subscript/superscript and heading-id overrides are general markdown
// features, not chat-specific like mentions/shortcodes/room-references, so
// a plain file preview gets them too.
export function preprocessMarkdown(text: string): { text: string; headingIds: Map<string, string> } {
  return extractHeadingIds(convertSubSuperscript(text))
}

// #71: Discord/Slack-style -- a message that's *nothing but* emoji renders
// them noticeably larger, no manual control needed. `\p{Extended_Pictographic}`
// is the standard way to match emoji in a JS regex (widely supported);
// `\p{Emoji_Modifier}` covers skin-tone modifiers, `\u200D` (zero-width
// joiner) covers compound emoji like family/profession sequences, and
// `\uFE0F` (variation selector-16) is the explicit emoji-presentation
// marker some single-codepoint emoji carry -- without all three a real
// multi-codepoint emoji cluster gets rejected partway through. A custom
// emoji's `:shortcode:` has no glyph to test against, so it's swapped for
// a placeholder pictograph first -- same substitution shape as
// convertCustomEmojiShortcodes above, just standing in for "yes, this is
// one emoji" rather than an actual image.
const EMOJI_ONLY_TEST = /^[\p{Extended_Pictographic}\p{Emoji_Modifier}\u200D\uFE0F]+$/u
// Discord's own cutoff for this treatment -- past a handful, "unusually
// large emoji" reads as spam rather than expressive, so it reverts to
// normal size instead of scaling a wall of them up.
const MAX_EMOJI_ONLY_COUNT = 20

export function isEmojiOnlyMessage(content: string, customShortcodes: Set<string>): boolean {
  const withBuiltinGlyphs = content.replace(SHORTCODE_PATTERN, (match, name) => EMOJI_SHORTCODES[name] ?? match)
  const withPlaceholders = withBuiltinGlyphs.replace(CUSTOM_EMOJI_PATTERN, (match, name) =>
    customShortcodes.has(name) ? '🔹' : match,
  )
  const stripped = withPlaceholders.replace(/\s+/g, '')
  if (!stripped || !EMOJI_ONLY_TEST.test(stripped)) return false
  return [...new Intl.Segmenter().segment(stripped)].length <= MAX_EMOJI_ONLY_COUNT
}

// #71: gives every individual unicode emoji its own element (see
// MarkdownLink's `glyph:` branch) purely so the emoji-size preference can
// scale it independently of the surrounding text -- a raw emoji is just
// characters in a string otherwise, with nothing CSS can address on its
// own. Runs after convertShortcodes so a built-in `:name:` that just
// became a glyph is wrapped too ("all emoji", not just ones typed as
// literal unicode); same fence/code-span skip convention as every other
// converter here.
const EMOJI_GLYPH_PATTERN = /\p{Extended_Pictographic}(?:\p{Emoji_Modifier}|\u200D\p{Extended_Pictographic}|\uFE0F)*/gu

function wrapEmojiGlyphs(text: string): string {
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
        .map((part, i) => (i % 2 === 0 ? part.replace(EMOJI_GLYPH_PATTERN, (match) => `[${match}](glyph:)`) : part))
        .join('')
    })
    .join('\n')
}

// Exported so MessageList's reaction pills can apply the same viewer
// preference to their own EmojiGlyph -- reactions render outside the
// markdown pipeline entirely (see EmojiGlyph's own comment above), so they
// need this looked up independently rather than inheriting --emoji-scale
// from this component's wrapper div.
export const EMOJI_SCALE_MULTIPLIER: Record<string, number> = {
  small: 0.8,
  normal: 1,
  large: 1.5,
  xlarge: 2,
}

export function MessageContent({ content, memberUsernames, myRooms }: MessageContentProps) {
  const { user } = useAuth()
  const { byShortcode } = useCustomEmoji()
  const customShortcodes = new Set(byShortcode.keys())
  const withMentions = memberUsernames ? highlightMentions(content, memberUsernames) : content
  const withRoomRefs = myRooms ? highlightRoomReferences(withMentions, myRooms) : withMentions
  const withCustomEmoji = convertCustomEmojiShortcodes(convertShortcodes(withRoomRefs), customShortcodes)
  const withEmojiGlyphs = wrapEmojiGlyphs(withCustomEmoji)
  const { text, headingIds } = preprocessMarkdown(withEmojiGlyphs)
  const emojiOnly = isEmojiOnlyMessage(content, customShortcodes)
  // #71: scoped to this element (not a :root-level variable) so it only
  // ever affects emoji rendered in message text -- not the same
  // .message-custom-emoji/EmojiGlyph markup reused by the emoji picker's
  // grid, where a bigger image would just break its fixed-size layout
  // instead of doing anything useful. Reaction pills DO scale too, but via
  // their own inline --emoji-scale in MessageList.tsx, not by inheriting
  // this one -- a pill isn't a descendant of this wrapper div.
  const emojiScale = EMOJI_SCALE_MULTIPLIER[user?.emoji_scale ?? 'normal']
  return (
    <div
      className={emojiOnly ? 'message-text-emoji-only' : undefined}
      style={{ '--emoji-scale': emojiScale } as CSSProperties}
    >
      <Markdown options={createMarkdownOptions(headingIds)}>{preserveLineBreaks(text)}</Markdown>
    </div>
  )
}

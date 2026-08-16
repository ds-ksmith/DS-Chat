import { useEffect, useState } from 'react'
import Markdown from 'markdown-to-jsx'
import { getRoomFileUrl } from '../api/rooms'
import { useEscapeKey } from '../hooks/useEscapeKey'
import type { MessageFileInfo } from '../types'
import { MARKDOWN_OPTIONS } from './MessageContent'
import './FilePreviewModal.css'

export type PreviewKind = 'markdown' | 'text'

// Deliberately extension-based, not content_type-based: the browser-supplied
// content_type for less-common extensions like .md is inconsistent (often
// reported as empty or application/octet-stream), so it isn't reliable
// enough to gate what gets parsed as markdown vs. shown as literal text.
export function getPreviewKind(filename: string): PreviewKind | null {
  const lower = filename.toLowerCase()
  if (lower.endsWith('.md') || lower.endsWith('.markdown')) return 'markdown'
  if (lower.endsWith('.txt')) return 'text'
  return null
}

interface FilePreviewModalProps {
  roomId: string
  file: MessageFileInfo
  kind: PreviewKind
  onClose: () => void
}

export function FilePreviewModal({ roomId, file, kind, onClose }: FilePreviewModalProps) {
  useEscapeKey(onClose)
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileUrl = getRoomFileUrl(roomId, file.id)

  useEffect(() => {
    let cancelled = false
    // A plain fetch() read is unaffected by the Content-Disposition:
    // attachment header the file-serve endpoint always sends -- that header
    // only steers the browser's own navigation/embed rendering, not a
    // script-initiated read of the response body. So no separate
    // "inline"-flavored endpoint is needed just to preview text.
    fetch(fileUrl, { credentials: 'include' })
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load file (${res.status})`)
        return res.text()
      })
      .then((text) => {
        if (!cancelled) setContent(text)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load file')
      })
    return () => {
      cancelled = true
    }
  }, [fileUrl])

  return (
    <div className="file-preview-overlay" onClick={onClose}>
      <div className="file-preview-modal" onClick={(e) => e.stopPropagation()}>
        <div className="file-preview-header">
          <span className="file-preview-filename">{file.filename}</span>
          <div className="file-preview-actions">
            <a href={fileUrl} download={file.filename} className="file-preview-download" aria-label="Download">
              <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path
                  d="M10 3v10m0 0-4-4m4 4 4-4M4 16h12"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </a>
            <button type="button" className="file-preview-close" onClick={onClose} aria-label="Close">
              ×
            </button>
          </div>
        </div>
        <div className="file-preview-body">
          {error && <p className="file-preview-error">{error}</p>}
          {!error && content === null && <p className="file-preview-loading">Loading…</p>}
          {!error && content !== null && kind === 'markdown' && (
            <div className="message-text file-preview-markdown">
              <Markdown options={MARKDOWN_OPTIONS}>{content}</Markdown>
            </div>
          )}
          {!error && content !== null && kind === 'text' && <pre className="file-preview-text">{content}</pre>}
        </div>
      </div>
    </div>
  )
}

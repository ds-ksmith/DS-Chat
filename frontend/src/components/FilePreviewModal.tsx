import { useEffect, useMemo, useState } from 'react'
import Markdown from 'markdown-to-jsx'
import { getRoomFileUrl } from '../api/rooms'
import { useEscapeKey } from '../hooks/useEscapeKey'
import type { MessageFileInfo } from '../types'
import { createMarkdownOptions, preprocessMarkdown } from './MessageContent'
import './FilePreviewModal.css'

export type PreviewKind = 'markdown' | 'text' | 'pdf'

// Deliberately extension-based, not content_type-based: the browser-supplied
// content_type for less-common extensions like .md is inconsistent (often
// reported as empty or application/octet-stream), so it isn't reliable
// enough to gate what gets parsed as markdown vs. shown as literal text.
export function getPreviewKind(filename: string): PreviewKind | null {
  const lower = filename.toLowerCase()
  if (lower.endsWith('.md') || lower.endsWith('.markdown')) return 'markdown'
  if (lower.endsWith('.txt')) return 'text'
  if (lower.endsWith('.pdf')) return 'pdf'
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
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileUrl = getRoomFileUrl(roomId, file.id)
  // #21: subscript/superscript and heading-id support -- see MessageContent
  // for why this needs to run before the Markdown component sees the text.
  const markdownPreview = useMemo(
    () => (content !== null ? preprocessMarkdown(content) : null),
    [content],
  )

  useEffect(() => {
    let cancelled = false
    let objectUrl: string | null = null
    // A plain fetch() read is unaffected by the Content-Disposition:
    // attachment header the file-serve endpoint always sends -- that header
    // only steers the browser's own navigation/embed rendering, not a
    // script-initiated read of the response body. So no separate
    // "inline"-flavored endpoint is needed just to preview text -- or, for
    // PDF, to preview it either: fetching the bytes ourselves and handing
    // the browser's native viewer a blob: URL (which carries no HTTP
    // headers of its own) sidesteps Content-Disposition the same way,
    // without needing an <iframe>/<embed> to navigate to the real file URL
    // directly (which *would* respect it and force a download).
    async function load() {
      const res = await fetch(fileUrl, { credentials: 'include' })
      if (!res.ok) throw new Error(`Failed to load file (${res.status})`)
      if (cancelled) return
      if (kind === 'pdf') {
        const blob = await res.blob()
        if (cancelled) return
        // Force the MIME type explicitly rather than trusting the server's
        // reported content_type -- getPreviewKind gates on the .pdf
        // extension alone (see its own comment), so a mislabeled upload
        // must still render as a PDF here, not download or error.
        objectUrl = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }))
        setPdfUrl(objectUrl)
      } else {
        const text = await res.text()
        if (!cancelled) setContent(text)
      }
    }
    load().catch((err) => {
      if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load file')
    })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [fileUrl, kind])

  return (
    <div className="file-preview-overlay" onClick={onClose}>
      <div
        className={`file-preview-modal${kind === 'pdf' ? ' file-preview-modal-pdf' : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
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
        <div className={`file-preview-body${kind === 'pdf' ? ' file-preview-body-pdf' : ''}`}>
          {error && <p className="file-preview-error">{error}</p>}
          {!error && kind !== 'pdf' && content === null && <p className="file-preview-loading">Loading…</p>}
          {!error && kind === 'markdown' && markdownPreview && (
            <div className="message-text file-preview-markdown">
              <Markdown options={createMarkdownOptions(markdownPreview.headingIds)}>
                {markdownPreview.text}
              </Markdown>
            </div>
          )}
          {!error && content !== null && kind === 'text' && <pre className="file-preview-text">{content}</pre>}
          {!error && kind === 'pdf' && !pdfUrl && <p className="file-preview-loading">Loading…</p>}
          {!error && kind === 'pdf' && pdfUrl && (
            <iframe src={pdfUrl} title={file.filename} className="file-preview-pdf-frame" />
          )}
        </div>
      </div>
    </div>
  )
}

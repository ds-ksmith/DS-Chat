import { useEffect, useMemo, useState } from 'react'
import Markdown from 'markdown-to-jsx'
import { Link } from 'react-router-dom'
import { createMarkdownOptions, preprocessMarkdown } from '../components/MessageContent'
import { TopBar } from '../components/TopBar'
import './HelpPage.css'

// Single source of truth is the repo-root USER_GUIDE.md -- frontend/public/
// symlinks to it, so this fetches the same file a developer sees when
// browsing the repo, rather than duplicating its content into the bundle.
const GUIDE_URL = '/USER_GUIDE.md'

export function HelpPage() {
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // #21: heading-id/sub/superscript support -- the user guide is exactly
  // the kind of document that benefits from an explicit anchor override.
  const markdownPreview = useMemo(
    () => (content !== null ? preprocessMarkdown(content) : null),
    [content],
  )

  useEffect(() => {
    let cancelled = false
    fetch(GUIDE_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load guide (${res.status})`)
        return res.text()
      })
      .then((text) => {
        if (!cancelled) setContent(text)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load guide')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="help-page">
      <TopBar />
      <div className="help-body">
        <div className="help-header">
          <h1>Help</h1>
          <Link to="/rooms" className="btn-secondary">
            Back to chat
          </Link>
        </div>
        {error && <p className="admin-error">{error}</p>}
        {!error && content === null && <p className="help-loading">Loading…</p>}
        {!error && markdownPreview && (
          <div className="message-text help-content">
            <Markdown options={createMarkdownOptions(markdownPreview.headingIds)}>
              {markdownPreview.text}
            </Markdown>
          </div>
        )}
      </div>
    </div>
  )
}

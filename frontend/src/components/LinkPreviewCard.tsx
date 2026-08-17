import type { LinkPreviewInfo } from '../types'
import './LinkPreviewCard.css'

interface LinkPreviewCardProps {
  preview: LinkPreviewInfo
}

// Slack/Discord-style unfurl card, rendered under a message's text when the
// backend found a URL in it and successfully fetched Open Graph data for it
// (see link_preview_service.py -- title/description/image_url/site_name are
// all independently optional, since not every page sets every og: tag).
export function LinkPreviewCard({ preview }: LinkPreviewCardProps) {
  return (
    <a
      href={preview.url}
      target="_blank"
      rel="noopener noreferrer"
      className="link-preview-card"
    >
      {preview.image_url && (
        <img src={preview.image_url} alt="" className="link-preview-image" loading="lazy" />
      )}
      <div className="link-preview-body">
        {preview.site_name && <span className="link-preview-site">{preview.site_name}</span>}
        {preview.title && <span className="link-preview-title">{preview.title}</span>}
        {preview.description && <span className="link-preview-description">{preview.description}</span>}
      </div>
    </a>
  )
}

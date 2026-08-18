import type { LinkPreviewInfo } from '../types'
import './LinkPreviewCard.css'

interface LinkPreviewCardProps {
  preview: LinkPreviewInfo
  onImageClick: (src: string) => void
}

// Slack/Discord-style unfurl card, rendered under a message's text when the
// backend found a URL in it and successfully fetched Open Graph data for it
// (see link_preview_service.py -- title/description/image_url/site_name are
// all independently optional, since not every page sets every og: tag).
export function LinkPreviewCard({ preview, onImageClick }: LinkPreviewCardProps) {
  // A direct link to an image file has no title/description/site_name to
  // show (there's no HTML page to scrape them from) -- render it the same
  // way a real image attachment renders (message-image + lightbox) rather
  // than the small unfurl card, which would otherwise show just a tiny
  // thumbnail with no text to go with it.
  if (preview.is_image && preview.image_url) {
    return (
      <img
        src={preview.image_url}
        alt=""
        className="message-image"
        onClick={() => onImageClick(preview.image_url!)}
      />
    )
  }

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

import { useEscapeKey } from '../hooks/useEscapeKey'
import './ImageLightbox.css'

interface ImageLightboxProps {
  src: string
  onClose: () => void
}

export function ImageLightbox({ src, onClose }: ImageLightboxProps) {
  useEscapeKey(onClose)

  return (
    <div className="image-lightbox" onClick={onClose}>
      <div className="image-lightbox-actions" onClick={(e) => e.stopPropagation()}>
        {/* Bare `download` (no explicit filename) -- MessageImage doesn't
            store an original filename, but the server response's own
            Content-Type header is enough for the browser to infer a
            sensible extension on its own. */}
        <a href={src} download className="image-lightbox-download" aria-label="Download">
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
        <button type="button" className="image-lightbox-close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      <img src={src} alt="" className="image-lightbox-img" />
    </div>
  )
}

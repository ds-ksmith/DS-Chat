import { useEscapeKey } from '../hooks/useEscapeKey'
import './ImageLightbox.css'
import './VideoLightbox.css'

interface VideoLightboxProps {
  src: string
  filename: string
  onClose: () => void
}

// #65 follow-up: requestFullscreen() on the inline <video> looked right in
// testing but silently did nothing in production -- the Fullscreen API can
// reject for reasons that don't show up as a visible error (permission
// policy, a standalone/installed PWA window disallowing it entirely), and
// nothing was catching that rejection. A lightbox has no such dependency --
// it's the same "expand" ImageLightbox already gives images, reusing its
// overlay/action-bar chrome directly (see the shared classNames below).
export function VideoLightbox({ src, filename, onClose }: VideoLightboxProps) {
  useEscapeKey(onClose)

  return (
    <div className="image-lightbox" onClick={onClose}>
      <div className="image-lightbox-actions" onClick={(e) => e.stopPropagation()}>
        <a href={src} download={filename} className="image-lightbox-download" aria-label="Download">
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
      {/* stopPropagation -- without it, clicking the video to play/pause
          (or seek, or hit any native control) also bubbles up to the
          overlay's onClose, closing the lightbox on the very interaction
          it exists to allow. */}
      <video
        src={src}
        controls
        autoPlay
        className="video-lightbox-video"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  )
}

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
      <img src={src} alt="" className="image-lightbox-img" />
    </div>
  )
}

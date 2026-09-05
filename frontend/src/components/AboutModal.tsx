import logo from '../assets/logo.png'
import './Modal.css'
import './AboutModal.css'

interface AboutModalProps {
  onClose: () => void
}

// AGPL-3.0 itself recommends this: "if your software can interact with
// users remotely through a computer network, you should also make sure
// that it provides a way for users to get its source... its interface
// could display a 'Source' link" -- this modal is that link, not just a
// courtesy credits screen. Deliberately not a hardcoded URL: whoever
// deploys this needs to point it at *their* copy of the repo (including
// any modifications), not the upstream project -- see frontend/.env.example.
const SOURCE_URL = import.meta.env.VITE_SOURCE_URL as string | undefined

export function AboutModal({ onClose }: AboutModalProps) {
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal about-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>About</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="about-modal-brand">
          <img src={logo} alt="" className="about-modal-logo" />
          <div>
            <div className="about-modal-name">DS Chat</div>
            <div className="about-modal-version">Version {__APP_VERSION__}</div>
          </div>
        </div>

        <p className="about-modal-line">
          Licensed under the{' '}
          <a href="/LICENSE" target="_blank" rel="noopener noreferrer">
            GNU Affero General Public License v3.0 (or later)
          </a>
          .
        </p>
        {SOURCE_URL && (
          <p className="about-modal-line">
            <a href={SOURCE_URL} target="_blank" rel="noopener noreferrer">
              Source code
            </a>
          </p>
        )}

        <div className="modal-actions" style={{ marginTop: '1rem' }}>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

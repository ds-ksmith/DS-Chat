import { useRef, useState, type KeyboardEvent } from 'react'
import './Composer.css'

interface ComposerProps {
  roomName: string
  disabled?: boolean
  onSend: (content: string) => void
}

export function Composer({ roomName, disabled, onSend }: ComposerProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  function autoGrow() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }

  function handleSend() {
    const trimmed = value.trim()
    if (!trimmed) return
    onSend(trimmed)
    setValue('')
    requestAnimationFrame(autoGrow)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="composer">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        disabled={disabled}
        onChange={(e) => {
          setValue(e.target.value)
          autoGrow()
        }}
        onKeyDown={handleKeyDown}
        placeholder={`Message #${roomName}`}
      />
      <button
        type="button"
        className="composer-send"
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        aria-label="Send message"
      >
        <svg width="15" height="15" viewBox="0 0 20 20" aria-hidden="true">
          <polygon points="2,2 18,10 2,18 6,10" fill="currentColor" />
        </svg>
      </button>
    </div>
  )
}

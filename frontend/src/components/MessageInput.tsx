import { useState, type FormEvent } from 'react'

interface MessageInputProps {
  disabled?: boolean
  onSend: (content: string) => void
}

export function MessageInput({ disabled, onSend }: MessageInputProps) {
  const [value, setValue] = useState('')

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = value.trim()
    if (!trimmed) return
    onSend(trimmed)
    setValue('')
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.5rem', padding: '0.5rem' }}>
      <input
        style={{ flex: 1 }}
        value={value}
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Message..."
      />
      <button type="submit" disabled={disabled || !value.trim()}>
        Send
      </button>
    </form>
  )
}

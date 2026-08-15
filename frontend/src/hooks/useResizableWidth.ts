import { useCallback, useEffect, useRef, useState, type PointerEvent } from 'react'

interface UseResizableWidthOptions {
  storageKey: string
  defaultWidth: number
  min: number
  max: number
  // 'right' (default): panel sits against the viewport's right edge, width
  // is measured from the cursor to that edge -- a handle on the panel's
  // LEFT edge drags naturally. 'left': panel sits against the left edge,
  // width is just the cursor's x position -- a handle on the panel's RIGHT
  // edge drags naturally.
  anchor?: 'left' | 'right'
}

// Persists to localStorage so it survives a reload.
export function useResizableWidth({
  storageKey,
  defaultWidth,
  min,
  max,
  anchor = 'right',
}: UseResizableWidthOptions) {
  const [width, setWidth] = useState(() => {
    const stored = Number(localStorage.getItem(storageKey))
    return stored >= min && stored <= max ? stored : defaultWidth
  })
  const widthRef = useRef(width)
  widthRef.current = width
  const draggingRef = useRef(false)

  useEffect(() => {
    function handleMove(e: PointerEvent<Window> | globalThis.PointerEvent) {
      if (!draggingRef.current) return
      const raw = anchor === 'left' ? e.clientX : window.innerWidth - e.clientX
      const next = Math.min(max, Math.max(min, raw))
      setWidth(next)
    }
    function handleUp() {
      if (!draggingRef.current) return
      draggingRef.current = false
      localStorage.setItem(storageKey, String(widthRef.current))
    }
    window.addEventListener('pointermove', handleMove as (e: globalThis.PointerEvent) => void)
    window.addEventListener('pointerup', handleUp)
    return () => {
      window.removeEventListener('pointermove', handleMove as (e: globalThis.PointerEvent) => void)
      window.removeEventListener('pointerup', handleUp)
    }
  }, [max, min, storageKey])

  const startResize = useCallback((e: PointerEvent) => {
    e.preventDefault()
    draggingRef.current = true
  }, [])

  return { width, startResize }
}

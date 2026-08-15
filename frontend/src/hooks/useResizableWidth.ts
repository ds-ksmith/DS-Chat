import { useCallback, useEffect, useRef, useState, type PointerEvent } from 'react'

interface UseResizableWidthOptions {
  storageKey: string
  defaultWidth: number
  min: number
  max: number
}

// Right-anchored resizable panel: width is the distance from the cursor to
// the viewport's right edge, so a handle on the panel's left edge drags
// naturally. Persists to localStorage so it survives a reload.
export function useResizableWidth({ storageKey, defaultWidth, min, max }: UseResizableWidthOptions) {
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
      const next = Math.min(max, Math.max(min, window.innerWidth - e.clientX))
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

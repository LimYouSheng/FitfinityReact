import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

/** One anchored, scrollable surface for field menus; stays inside its existing modal layer. */
export default function FieldPopover({ anchorRef, onClose, width, children, ...props }) {
  const ref = useRef(null)
  const [position, setPosition] = useState({ visibility: 'hidden' })
  useLayoutEffect(() => {
    const place = () => {
      const anchor = anchorRef.current
      if (!anchor) return
      const rect = anchor.getBoundingClientRect()
      const viewport = window.visualViewport
      const top = viewport?.offsetTop ?? 0
      const left = viewport?.offsetLeft ?? 0
      const height = viewport?.height ?? window.innerHeight
      const availableWidth = viewport?.width ?? window.innerWidth
      const menuWidth = Math.min(width ?? Math.max(rect.width, 180), availableWidth - 24)
      const below = top + height - rect.bottom - 12
      const above = rect.top - top - 12
      const upwards = below < 240 && above > below
      const maxHeight = Math.max(80, Math.min(360, height * .6, (upwards ? above : below) - 5))
      setPosition({ width: menuWidth, maxHeight,
        left: Math.max(left + 12, Math.min(rect.left, left + availableWidth - menuWidth - 12)),
        ...(upwards ? { bottom: window.innerHeight - rect.top + 5 } : { top: rect.bottom + 5 }) })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    window.visualViewport?.addEventListener('resize', place)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
      window.visualViewport?.removeEventListener('resize', place)
    }
  }, [anchorRef, width])
  useEffect(() => {
    const outside = event => {
      if (!anchorRef.current?.contains(event.target) && !ref.current?.contains(event.target)) onClose()
    }
    const keyboard = event => {
      if ([...document.querySelectorAll('.field-popover')].at(-1) !== ref.current) return
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onClose(); anchorRef.current?.focus({ preventScroll: true }) }
    }
    document.addEventListener('pointerdown', outside, true)
    document.addEventListener('keydown', keyboard, true)
    return () => {
      document.removeEventListener('pointerdown', outside, true)
      document.removeEventListener('keydown', keyboard, true)
    }
  }, [anchorRef, onClose])
  // Keep choices inside their edit/confirmation owner so its click guard permits them.
  // Nested month/year menus also remain inside their calendar's outside-click boundary.
  const host = anchorRef.current?.closest('.field-popover, .editing-section, .modal-backdrop, [data-modal-layer]') ?? document.getElementById('root') ?? document.body
  return createPortal(<div {...props} ref={ref} className={`field-popover ${props.className ?? ''}`} style={position}>{children}</div>, host)
}

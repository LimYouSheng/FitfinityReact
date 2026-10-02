import { useRef } from 'react'

/** Native fields may omit click when pointerdown default behavior is prevented. Activate a tap on release. */
export default function useFieldActivation(activate) {
  const contact = useRef(null)
  const directPointer = useRef(false)
  const moved = (event, start) => Math.hypot(event.clientX - start.x, event.clientY - start.y) > 10
  const cancel = () => { contact.current = null }
  return {
    onPointerDown(event) {
      // Suppress the native picker/focus, while leaving browser panning enabled.
      event.preventDefault()
      directPointer.current = event.pointerType === 'touch' || event.pointerType === 'pen'
      contact.current = directPointer.current && event.isPrimary && event.button === 0
        ? { id: event.pointerId, x: event.clientX, y: event.clientY } : null
    },
    onPointerMove(event) {
      const start = contact.current
      if (start?.id === event.pointerId && moved(event, start)) cancel()
    },
    onPointerCancel: cancel,
    onLostPointerCapture: cancel,
    onPointerUp(event) {
      const start = contact.current
      if (!start || start.id !== event.pointerId) return
      cancel()
      const rect = event.currentTarget.getBoundingClientRect()
      if (moved(event, start) || event.clientX < rect.left || event.clientX > rect.right
        || event.clientY < rect.top || event.clientY > rect.bottom) return
      activate(event)
    },
    onMouseDown: event => event.preventDefault(),
    onClick(event) {
      event.preventDefault()
      // Touch/pen was handled on release (or cancelled). Keyboard/AT clicks remain valid.
      if (!directPointer.current || event.detail === 0) activate(event)
    },
  }
}

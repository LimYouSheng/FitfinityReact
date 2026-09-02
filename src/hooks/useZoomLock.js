import { useEffect } from 'react'

function scrollableAncestorCanMoveUp(target) {
  let element = target instanceof Element ? target : null

  while (element && element !== document.documentElement) {
    const style = getComputedStyle(element)
    const overflowY = style.overflowY
    const scrollable =
      (overflowY === 'auto' || overflowY === 'scroll') &&
      element.scrollHeight > element.clientHeight

    if (scrollable && element.scrollTop > 0) {
      return true
    }

    element = element.parentElement
  }

  return false
}

export default function useZoomLock() {
  useEffect(() => {
    let touchStartY = 0

    const prevent = event => {
      if (event.cancelable) event.preventDefault()
    }

    const onTouchStart = event => {
      if (event.touches.length > 1) {
        prevent(event)
        return
      }

      touchStartY = event.touches[0]?.clientY ?? 0
    }

    const onTouchMove = event => {
      if (event.touches.length > 1) {
        prevent(event)
        return
      }

      const touch = event.touches[0]
      if (!touch) return

      const movingDown = touch.clientY > touchStartY + 2
      const pageAtTop =
        window.scrollY <= 0 &&
        (document.scrollingElement?.scrollTop ?? 0) <= 0

      if (
        movingDown &&
        pageAtTop &&
        !scrollableAncestorCanMoveUp(event.target)
      ) {
        prevent(event)
      }
    }

    const preventWheelZoom = event => {
      if (event.ctrlKey || event.metaKey) prevent(event)
    }

    const preventKeyboardZoom = event => {
      if (!(event.ctrlKey || event.metaKey)) return
      if (['+', '-', '=', '0'].includes(event.key)) prevent(event)
    }

    document.addEventListener('gesturestart', prevent, { passive: false, capture: true })
    document.addEventListener('gesturechange', prevent, { passive: false, capture: true })
    document.addEventListener('gestureend', prevent, { passive: false, capture: true })
    document.addEventListener('touchstart', onTouchStart, { passive: false, capture: true })
    document.addEventListener('touchmove', onTouchMove, { passive: false, capture: true })
    window.addEventListener('wheel', preventWheelZoom, { passive: false, capture: true })
    window.addEventListener('keydown', preventKeyboardZoom, true)

    return () => {
      document.removeEventListener('gesturestart', prevent, true)
      document.removeEventListener('gesturechange', prevent, true)
      document.removeEventListener('gestureend', prevent, true)
      document.removeEventListener('touchstart', onTouchStart, true)
      document.removeEventListener('touchmove', onTouchMove, true)
      window.removeEventListener('wheel', preventWheelZoom, true)
      window.removeEventListener('keydown', preventKeyboardZoom, true)
    }
  }, [])
}

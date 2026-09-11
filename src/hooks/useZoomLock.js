import { useEffect } from 'react'

export default function useZoomLock() {
  useEffect(() => {
    const prevent = event => {
      if (event.cancelable) event.preventDefault()
    }

    // The browser owns one-finger panning. CSS suppresses boundary refresh;
    // cancelling a vertical touchmove here can cancel the whole scroll gesture.
    const preventPinchZoom = event => {
      if (event.touches.length > 1) prevent(event)
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
    document.addEventListener('touchstart', preventPinchZoom, { passive: false, capture: true })
    document.addEventListener('touchmove', preventPinchZoom, { passive: false, capture: true })
    window.addEventListener('wheel', preventWheelZoom, { passive: false, capture: true })
    window.addEventListener('keydown', preventKeyboardZoom, true)

    return () => {
      document.removeEventListener('gesturestart', prevent, true)
      document.removeEventListener('gesturechange', prevent, true)
      document.removeEventListener('gestureend', prevent, true)
      document.removeEventListener('touchstart', preventPinchZoom, true)
      document.removeEventListener('touchmove', preventPinchZoom, true)
      window.removeEventListener('wheel', preventWheelZoom, true)
      window.removeEventListener('keydown', preventKeyboardZoom, true)
    }
  }, [])
}

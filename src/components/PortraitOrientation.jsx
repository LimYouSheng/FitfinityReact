import { useEffect, useState } from 'react'
import ModalPortal from './ModalPortal.jsx'

/** Request the native PWA lock; preserve mounted forms behind the fallback on unsupported devices. */
export default function PortraitOrientation() {
  const [landscape, setLandscape] = useState(false)

  useEffect(() => {
    const touchDevice = window.matchMedia('(pointer: coarse)').matches ||
      (navigator.maxTouchPoints > 0 && (/Android|iPhone|iPad|iPod/.test(navigator.userAgent) || navigator.platform === 'MacIntel'))
    if (!touchDevice) return

    const orientation = window.screen.orientation
    const installed = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true
    const requestLock = () => {
      if (!installed || typeof orientation?.lock !== 'function' || document.hidden) return
      try { Promise.resolve(orientation.lock('portrait')).catch(() => {}) }
      catch { /* Unsupported native locks use the same portrait fallback. */ }
    }
    const update = () => {
      // Physical screen orientation avoids treating the portrait keyboard as a rotation.
      const rotated = orientation?.type
        ? orientation.type.startsWith('landscape')
        : typeof window.orientation === 'number'
          ? Math.abs(window.orientation) === 90
          : window.screen.width > window.screen.height
      setLandscape(rotated)
    }
    const onOrientation = () => { update(); requestLock() }
    const onVisible = () => { if (!document.hidden) onOrientation() }
    update()
    requestLock()
    orientation?.addEventListener?.('change', onOrientation)
    window.addEventListener('orientationchange', onOrientation)
    window.addEventListener('resize', update)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      orientation?.removeEventListener?.('change', onOrientation)
      window.removeEventListener('orientationchange', onOrientation)
      window.removeEventListener('resize', update)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  if (!landscape) return null
  return (
    <ModalPortal>
      <div className="portrait-orientation" role="dialog" aria-modal="true" aria-labelledby="portrait-orientation-title">
        <div>
          <h1 id="portrait-orientation-title">Please rotate your device</h1>
          <p>Use Fitfinity in portrait on your phone or tablet.</p>
        </div>
      </div>
    </ModalPortal>
  )
}

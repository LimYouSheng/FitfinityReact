import { useEffect } from 'react'

const VIEWPORT_EDGE_WIDTH = 72
const PAGE_EDGE_LEEWAY = 16
const PAGE_EDGE_WIDTH = 72

function historyToken() {
  return [
    location.hash,
    history.state?.fitfinityDepth ?? '',
    history.state?.fitfinityOverlayId ?? '',
  ].join('|')
}

function pageElement() {
  return document.querySelector('.portal-main')
}

function applyDrag(element, x) {
  if (!element) return

  const capped = Math.max(0, Math.min(x, window.innerWidth * 0.72))
  const progress = Math.min(capped / Math.max(window.innerWidth, 1), 1)

  element.style.transition = 'none'
  element.style.transform = `translate3d(${capped}px,0,0)`
  element.style.boxShadow = `-18px 0 44px rgba(0,0,0,${0.08 + progress * 0.22})`
  element.style.willChange = 'transform'
}

function resetDrag(element, animated = true) {
  if (!element) return

  element.style.transition = animated
    ? 'transform 180ms ease-out, box-shadow 180ms ease-out'
    : 'none'

  element.style.transform = 'translate3d(0,0,0)'
  element.style.boxShadow = ''
  element.style.willChange = ''

  if (animated) {
    window.setTimeout(() => {
      if (!element) return
      element.style.transition = ''
    }, 200)
  }
}

function commitDrag(element) {
  if (!element) return

  element.style.transition = 'transform 150ms ease-in, box-shadow 150ms ease-in'
  element.style.transform = `translate3d(${window.innerWidth}px,0,0)`
  element.style.boxShadow = '-24px 0 52px rgba(0,0,0,.32)'
}

export default function useSwipeBack({ enabled, onBack }) {
  useEffect(() => {
    if (!enabled) return undefined

    let tracking = false
    let startX = 0
    let startY = 0
    let currentX = 0
    let startToken = ''
    let lastTouchStartedAt = 0
    let directionLocked = false
    let horizontalGesture = false

    const begin = (x, y) => {
      const pageLeft = pageElement()?.getBoundingClientRect().left ?? 0
      const atViewportEdge = x <= VIEWPORT_EDGE_WIDTH
      const atPageEdge =
        x >= pageLeft - PAGE_EDGE_LEEWAY &&
        x <= pageLeft + PAGE_EDGE_WIDTH

      if (!atViewportEdge && !atPageEdge) return

      tracking = true
      startX = x
      startY = y
      currentX = x
      startToken = historyToken()
      directionLocked = false
      horizontalGesture = false
    }

    const move = (x, y, event) => {
      if (!tracking) return

      const deltaX = x - startX
      const deltaY = y - startY

      currentX = x

      if (!directionLocked && (Math.abs(deltaX) > 8 || Math.abs(deltaY) > 8)) {
        directionLocked = true
        horizontalGesture =
          deltaX > 0 &&
          Math.abs(deltaX) > Math.abs(deltaY) * 1.1
      }

      if (!horizontalGesture) return

      if (event?.cancelable) event.preventDefault()
      applyDrag(pageElement(), deltaX)
    }

    const finish = (x, y) => {
      if (!tracking) return
      tracking = false

      const deltaX = x - startX
      const deltaY = Math.abs(y - startY)
      const element = pageElement()

      const shouldGoBack =
        horizontalGesture &&
        deltaX >= Math.min(92, window.innerWidth * 0.24) &&
        deltaY < 110

      if (!shouldGoBack) {
        resetDrag(element, true)
        return
      }

      // Native browser history may already complete a left-edge gesture.
      // If not, animate the app page off-screen before invoking app history.
      window.setTimeout(() => {
        if (historyToken() !== startToken) {
          resetDrag(element, false)
          return
        }

        commitDrag(element)

        window.setTimeout(() => {
          onBack()
          window.requestAnimationFrame(() => resetDrag(element, false))
        }, 145)
      }, 70)
    }

    const cancel = () => {
      tracking = false
      resetDrag(pageElement(), true)
    }

    const onTouchStart = event => {
      if (event.target.closest?.('[data-no-swipe]')) return
      const touch = event.touches?.[0]
      if (!touch) return

      const target = event.target
      if (
        target instanceof Element &&
        target.closest('input, textarea, select, [contenteditable="true"]')
      ) {
        return
      }

      lastTouchStartedAt = Date.now()
      begin(touch.clientX, touch.clientY)
    }

    const onTouchMove = event => {
      const touch = event.touches?.[0]
      if (!touch) return
      move(touch.clientX, touch.clientY, event)
    }

    const onTouchEnd = event => {
      const touch = event.changedTouches?.[0]
      if (!touch) return
      finish(touch.clientX, touch.clientY)
    }

    const onPointerDown = event => {
      if (event.target.closest?.('[data-no-swipe]')) return
      if (event.pointerType === 'mouse') return
      if (Date.now() - lastTouchStartedAt < 600) return

      const target = event.target
      if (
        target instanceof Element &&
        target.closest('input, textarea, select, [contenteditable="true"]')
      ) {
        return
      }

      begin(event.clientX, event.clientY)
    }

    const onPointerMove = event => {
      if (event.pointerType === 'mouse') return
      if (Date.now() - lastTouchStartedAt < 600) return
      move(event.clientX, event.clientY, event)
    }

    const onPointerUp = event => {
      if (event.pointerType === 'mouse') return
      if (Date.now() - lastTouchStartedAt < 600) return
      finish(event.clientX, event.clientY)
    }

    window.addEventListener('touchstart', onTouchStart, {
      passive: true,
      capture: true,
    })

    window.addEventListener('touchmove', onTouchMove, {
      passive: false,
      capture: true,
    })

    window.addEventListener('touchend', onTouchEnd, {
      passive: true,
      capture: true,
    })

    window.addEventListener('touchcancel', cancel, {
      passive: true,
      capture: true,
    })

    window.addEventListener('pointerdown', onPointerDown, {
      passive: true,
      capture: true,
    })

    window.addEventListener('pointermove', onPointerMove, {
      passive: false,
      capture: true,
    })

    window.addEventListener('pointerup', onPointerUp, {
      passive: true,
      capture: true,
    })

    window.addEventListener('pointercancel', cancel, {
      passive: true,
      capture: true,
    })

    return () => {
      resetDrag(pageElement(), false)

      window.removeEventListener('touchstart', onTouchStart, true)
      window.removeEventListener('touchmove', onTouchMove, true)
      window.removeEventListener('touchend', onTouchEnd, true)
      window.removeEventListener('touchcancel', cancel, true)

      window.removeEventListener('pointerdown', onPointerDown, true)
      window.removeEventListener('pointermove', onPointerMove, true)
      window.removeEventListener('pointerup', onPointerUp, true)
      window.removeEventListener('pointercancel', cancel, true)
    }
  }, [enabled, onBack])
}

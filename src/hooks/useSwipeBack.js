import { useEffect, useRef } from 'react'

const EDGE_WIDTH = 72
const PAGE_EDGE_LEEWAY = 16
const historyToken = () => [location.hash, history.state?.fitfinityDepth ?? '', history.state?.fitfinityOverlayId ?? ''].join('|')

function resetDrag(element, animated = false) {
  if (!element) return
  element.style.transition = animated ? 'transform 180ms ease-out, box-shadow 180ms ease-out' : ''
  element.style.transform = ''
  element.style.boxShadow = ''
  element.style.willChange = ''
}

export default function useSwipeBack({ enabled, onBack, routeKey = '', surface = '.portal-main' }) {
  const back = useRef(onBack)
  back.current = onBack
  useEffect(() => {
    if (!enabled) return
    let gesture = null
    let lastTouch = -Infinity
    let activeTouch = false
    const timers = new Set()
    const later = (action, delay) => {
      const timer = window.setTimeout(() => { timers.delete(timer); action() }, delay)
      timers.add(timer)
    }
    const clearTimers = () => { for (const timer of timers) window.clearTimeout(timer); timers.clear() }
    const cancel = () => {
      clearTimers()
      resetDrag(gesture?.element)
      gesture = null
    }
    const begin = (x, y, target, pointerId) => {
      cancel()
      const element = document.querySelector(surface)
      const modal = [...document.querySelectorAll('[data-modal-layer]')].at(-1)
      // A popup or drawer owns its gestures; never drag its inert background.
      if (!element || element.closest('[inert]') || (modal && !modal.contains(element)) || document.querySelector('.sidebar.mobile-open')) return
      if (target instanceof Element && (!element.contains(target) || target.closest('[data-no-swipe],input,textarea,select,[contenteditable="true"]'))) return
      const pageLeft = element.getBoundingClientRect().left
      if (x > EDGE_WIDTH && (x < pageLeft - PAGE_EDGE_LEEWAY || x > pageLeft + EDGE_WIDTH)) return
      gesture = { element, x, y, token: historyToken(), pointerId, direction: null, ending: false }
    }
    const move = (x, y, event) => {
      if (!gesture || gesture.ending) return
      const dx = x - gesture.x, dy = y - gesture.y
      if (gesture.direction === null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) gesture.direction = dx > 0 && Math.abs(dx) > Math.abs(dy) * 1.1
      if (!gesture.direction) return
      if (event.cancelable) event.preventDefault()
      const distance = Math.max(0, Math.min(dx, window.innerWidth * 0.72))
      Object.assign(gesture.element.style, { transition: 'none', transform: `translate3d(${distance}px,0,0)`,
        boxShadow: `-18px 0 44px rgba(0,0,0,${0.08 + distance / Math.max(window.innerWidth, 1) * 0.22})`, willChange: 'transform' })
    }
    const finish = (x, y) => {
      if (!gesture || gesture.ending) return
      const current = gesture
      current.ending = true
      if (!current.direction || x - current.x < Math.min(92, window.innerWidth * 0.24) || Math.abs(y - current.y) >= 110) {
        resetDrag(current.element, true)
        later(cancel, 200)
        return
      }
      // Native browser Back may finish the same edge gesture. Check both before
      // and after animation so it can never be followed by a second app Back.
      later(() => {
        if (historyToken() !== current.token) { cancel(); return }
        Object.assign(current.element.style, { transition: 'transform 150ms ease-in, box-shadow 150ms ease-in',
          transform: `translate3d(${window.innerWidth}px,0,0)`, boxShadow: '-24px 0 52px rgba(0,0,0,.32)' })
        later(() => {
          const unchanged = historyToken() === current.token
          cancel()
          if (unchanged) void back.current()
        }, 145)
      }, 70)
    }
    const touchStart = event => {
      lastTouch = performance.now()
      activeTouch = event.touches.length > 0
      if (event.touches.length !== 1) { cancel(); return }
      const touch = event.touches[0]
      begin(touch.clientX, touch.clientY, event.target, touch.identifier)
    }
    const touchMove = event => {
      if (event.touches.length !== 1) { cancel(); return }
      const touch = event.touches[0]
      if (touch.identifier === gesture?.pointerId) move(touch.clientX, touch.clientY, event)
    }
    const touchEnd = event => {
      activeTouch = event.touches.length > 0
      lastTouch = performance.now()
      const touch = [...event.changedTouches].find(item => item.identifier === gesture?.pointerId)
      if (touch) finish(touch.clientX, touch.clientY)
    }
    const touchCancel = () => { activeTouch = false; lastTouch = performance.now(); cancel() }
    const pointerStart = event => {
      if (event.pointerType === 'mouse' || activeTouch || performance.now() - lastTouch < 600) return
      if (event.isPrimary === false) { cancel(); return }
      begin(event.clientX, event.clientY, event.target, event.pointerId)
    }
    const pointerMove = event => {
      if (event.pointerType !== 'mouse' && !activeTouch && performance.now() - lastTouch >= 600 && event.pointerId === gesture?.pointerId) move(event.clientX, event.clientY, event)
    }
    const pointerEnd = event => {
      if (event.pointerType !== 'mouse' && !activeTouch && performance.now() - lastTouch >= 600 && event.pointerId === gesture?.pointerId) finish(event.clientX, event.clientY)
    }
    const pointerCancel = () => { if (!activeTouch && performance.now() - lastTouch >= 600) cancel() }
    const preventSwipeClick = event => {
      if (gesture?.ending && gesture.direction) { event.preventDefault(); event.stopPropagation() }
    }
    const listeners = { touchstart: touchStart, touchmove: touchMove, touchend: touchEnd, touchcancel: touchCancel,
      pointerdown: pointerStart, pointermove: pointerMove, pointerup: pointerEnd, pointercancel: pointerCancel, click: preventSwipeClick }
    for (const [name, handler] of Object.entries(listeners)) window.addEventListener(name, handler, { capture: true, passive: !['touchmove', 'pointermove', 'click'].includes(name) })
    return () => {
      cancel()
      for (const [name, handler] of Object.entries(listeners)) window.removeEventListener(name, handler, true)
    }
  }, [enabled, routeKey, surface])
}

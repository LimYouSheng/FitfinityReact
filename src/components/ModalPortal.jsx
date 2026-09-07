import { useLayoutEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

let openModalCount = 0
let lockedScrollPosition = { x: 0, y: 0 }
let savedPageStyles = null

function lockPageScroll() {
  if (openModalCount === 0) {
    const body = document.body
    const root = document.documentElement

    lockedScrollPosition = { x: window.scrollX, y: window.scrollY }
    savedPageStyles = {
      bodyOverflow: body.style.overflow,
      bodyPosition: body.style.position,
      bodyTop: body.style.top,
      bodyLeft: body.style.left,
      bodyRight: body.style.right,
      bodyWidth: body.style.width,
      rootOverflow: root.style.overflow,
      rootOverscrollBehavior: root.style.overscrollBehavior,
    }

    root.style.overflow = 'hidden'
    root.style.overscrollBehavior = 'none'
    body.style.overflow = 'hidden'
    body.style.position = 'fixed'
    body.style.top = `-${lockedScrollPosition.y}px`
    body.style.left = `-${lockedScrollPosition.x}px`
    body.style.right = '0'
    body.style.width = '100%'
  }

  openModalCount += 1
}

function unlockPageScroll() {
  openModalCount = Math.max(0, openModalCount - 1)
  if (openModalCount > 0 || !savedPageStyles) return

  const body = document.body
  const root = document.documentElement

  body.style.overflow = savedPageStyles.bodyOverflow
  body.style.position = savedPageStyles.bodyPosition
  body.style.top = savedPageStyles.bodyTop
  body.style.left = savedPageStyles.bodyLeft
  body.style.right = savedPageStyles.bodyRight
  body.style.width = savedPageStyles.bodyWidth
  root.style.overflow = savedPageStyles.rootOverflow
  root.style.overscrollBehavior = savedPageStyles.rootOverscrollBehavior
  savedPageStyles = null

  if (lockedScrollPosition.x || lockedScrollPosition.y) {
    window.scrollTo(lockedScrollPosition.x, lockedScrollPosition.y)
  }
}

const modalLayers = []
const originalInert = new Map()
const FOCUSABLE = 'button,input,select,textarea,a[href],[tabindex]'

function focusable(root) {
  return [...root.querySelectorAll(FOCUSABLE)].filter(element => {
    if (element.disabled || element.tabIndex < 0 || element.closest('[inert],[hidden]')) return false
    for (let parent = element; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent)
      if (style.display === 'none' || style.visibility === 'hidden') return false
    }
    return true
  })
}

function isolateLayers() {
  const active = modalLayers.at(-1)?.element
  for (const child of document.body.children) {
    if (!originalInert.has(child)) originalInert.set(child, child.hasAttribute('inert'))
    if (active && child !== active && !child.matches('.notification-region')) child.setAttribute('inert', '')
    else if (!originalInert.get(child)) child.removeAttribute('inert')
  }
  if (!active) {
    for (const [element, wasInert] of originalInert) {
      if (wasInert) element.setAttribute('inert', '')
      else element.removeAttribute('inert')
    }
    originalInert.clear()
  }
}

function focusDialog(element) {
  const dialog = element.querySelector('[role="dialog"]') ?? element
  const target = dialog.querySelector('[data-modal-initial-focus]') ?? focusable(dialog)[0]
  if (target) target.focus({ preventScroll: true })
  else {
    dialog.setAttribute('tabindex', '-1')
    dialog.focus({ preventScroll: true })
  }
}

export default function ModalPortal({ children }) {
  const elementRef = useRef(null)
  useLayoutEffect(() => {
    const layer = { element: elementRef.current, opener: document.activeElement }
    modalLayers.push(layer)
    lockPageScroll()
    isolateLayers()
    focusDialog(layer.element)

    const isActive = () => modalLayers.at(-1) === layer
    const allowedRoots = () => [layer.element, ...document.querySelectorAll('.notification-region')]
    const keepFocus = event => {
      if (isActive() && !allowedRoots().some(root => root.contains(event.target))) focusDialog(layer.element)
    }
    const onKeyDown = event => {
      if (!isActive() || event.key !== 'Tab') return
      const targets = allowedRoots().flatMap(focusable)
      const index = targets.indexOf(document.activeElement)
      event.preventDefault()
      const next = index < 0 ? (event.shiftKey ? targets.length - 1 : 0)
        : (index + (event.shiftKey ? -1 : 1) + targets.length) % targets.length
      if (targets[next]) targets[next].focus({ preventScroll: true })
      else focusDialog(layer.element)
    }
    const observer = new MutationObserver(() => {
      if (!isActive()) return
      isolateLayers()
      if (!allowedRoots().some(root => root.contains(document.activeElement))) focusDialog(layer.element)
    })
    observer.observe(document.body, { childList: true, subtree: true })
    document.addEventListener('focusin', keepFocus)
    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      observer.disconnect()
      document.removeEventListener('focusin', keepFocus)
      document.removeEventListener('keydown', onKeyDown, true)
      const wasActive = isActive()
      modalLayers.splice(modalLayers.indexOf(layer), 1)
      isolateLayers()
      unlockPageScroll()
      if (wasActive) {
        const next = modalLayers.at(-1)
        if (layer.opener?.isConnected && !layer.opener.closest('[inert]') && (!next || next.element.contains(layer.opener))) {
          layer.opener.focus({ preventScroll: true })
        } else if (next) focusDialog(next.element)
      }
    }
  }, [])
  return createPortal(<div ref={elementRef} data-modal-layer="">{children}</div>, document.body)
}

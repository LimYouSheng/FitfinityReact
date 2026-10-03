import { useLayoutEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import usePageScrollLock from '../hooks/usePageScrollLock.js'

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
  usePageScrollLock()
  useLayoutEffect(() => {
    const layer = { element: elementRef.current, opener: document.activeElement, parent: modalLayers.at(-1) }
    modalLayers.push(layer)
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
      // Preserve the stack relationship even if a touch click left focus on
      // the body. A removed parent must pass its return target to its child.
      for (const remaining of modalLayers) {
        if (remaining !== layer && (remaining.parent === layer || layer.element.contains(remaining.opener))) {
          remaining.opener = layer.opener
          remaining.parent = layer.parent
        }
      }
      modalLayers.splice(modalLayers.indexOf(layer), 1)
      isolateLayers()
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

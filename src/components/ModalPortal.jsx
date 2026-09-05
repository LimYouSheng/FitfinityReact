import { useEffect } from 'react'
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

export default function ModalPortal({ children }) {
  useEffect(() => {
    lockPageScroll()
    return unlockPageScroll
  }, [])

  return createPortal(children, document.body)
}

import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render } from '@testing-library/react'
import useSwipeBack from './useSwipeBack.js'
import useZoomLock from './useZoomLock.js'

function Harness({ onBack, routeKey = 'clients/c1', modal = false }) {
  useZoomLock()
  useSwipeBack({ enabled: true, onBack, routeKey })
  useSwipeBack({ enabled: modal, onBack: () => onBack('modal'), routeKey, surface: '.message-detail-modal' })
  return <><main className="portal-main"><div data-testid="content">Client</div><input /></main>
    {modal && <div data-modal-layer><div className="message-detail-modal">Message</div></div>}</>
}
const surface = () => document.querySelector('.portal-main')
const touch = (type, x, y = 180, target = surface(), count = 1) => {
  const point = { identifier: 7, clientX: x, clientY: y }
  const event = Object.assign(new Event(type, { bubbles: true, cancelable: true }), {
    touches: type === 'touchend' ? [] : Array(count).fill(point), changedTouches: [point],
  })
  fireEvent(target, event)
  return event
}
const swipe = target => { touch('touchstart', 10, 180, target); touch('touchmove', 160, 186, target); touch('touchend', 180, 190, target) }
const settle = () => act(() => vi.advanceTimersByTime(500))
beforeEach(() => { vi.useFakeTimers(); history.replaceState({ fitfinityDepth: 2 }, '', '/#/clients/c1') })
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks() })

it('retains an active touch through a data rerender and calls the latest Back once', () => {
  const oldBack = vi.fn(), newBack = vi.fn()
  const view = render(<Harness onBack={oldBack} />)
  touch('touchstart', 10)
  view.rerender(<Harness onBack={newBack} />)
  touch('touchmove', 160)
  expect(surface().style.transform).toContain('150px')
  touch('touchend', 180); settle()
  expect(newBack).toHaveBeenCalledExactlyOnceWith()
  expect(oldBack).not.toHaveBeenCalled()
  expect(surface().style.transform).toBe('')
})

it('does not lose a real touch gesture when the browser also cancels its pointer stream', () => {
  for (const hold of [0, 800]) {
    const back = vi.fn(); render(<Harness onBack={back} />)
    touch('touchstart', 10)
    act(() => vi.advanceTimersByTime(hold))
    fireEvent(surface(), Object.assign(new Event('pointercancel', { bubbles: true }), { pointerType: 'touch' }))
    touch('touchmove', 160); touch('touchend', 180); settle()
    expect(back).toHaveBeenCalledTimes(1)
    cleanup()
  }
})

it.each([30, 100])('avoids a second Back when native history traverses after %i ms', delay => {
  const back = vi.fn(); render(<Harness onBack={back} />)
  swipe(); act(() => vi.advanceTimersByTime(delay))
  history.replaceState({ fitfinityDepth: 1 }, '', '/#/clients')
  settle()
  expect(back).not.toHaveBeenCalled()
  expect(surface().style.transform).toBe('')
})

it('cancels queued navigation and resets the page when its route changes or it unmounts', () => {
  const back = vi.fn(); const view = render(<Harness onBack={back} />)
  swipe(); view.rerender(<Harness onBack={back} routeKey="trainers" />); settle()
  expect(back).not.toHaveBeenCalled()
  expect(surface().style.transform).toBe('')
  swipe(); view.unmount(); settle()
  expect(back).not.toHaveBeenCalled()
})

it('gives an open popup sole ownership of a swipe without moving the background page', () => {
  const back = vi.fn(); render(<Harness onBack={back} modal />)
  swipe(surface()); settle(); expect(back).not.toHaveBeenCalled()
  swipe(document.querySelector('.message-detail-modal')); settle()
  expect(back).toHaveBeenCalledExactlyOnceWith('modal')
  expect(surface().style.transform).toBe('')
})

it('leaves vertical scrolling, fields, short drags, multitouch and open drawers alone', () => {
  const back = vi.fn(); render(<Harness onBack={back} />)
  // Exercise the installed zoom lock and swipe hook together. A slight downward
  // start must not cancel native scrolling or a subsequent upward movement.
  expect(touch('touchstart', 160, 180).defaultPrevented).toBe(false)
  expect(touch('touchmove', 160, 185).defaultPrevented).toBe(false)
  expect(touch('touchmove', 160, 100).defaultPrevented).toBe(false)
  touch('touchend', 160, 100); settle()
  touch('touchstart', 10, 180)
  expect(touch('touchmove', 12, 240).defaultPrevented).toBe(false)
  touch('touchend', 12, 240); settle()
  const wheel = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: 100 })
  fireEvent(surface(), wheel)
  expect(wheel.defaultPrevented).toBe(false)
  const zoom = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: 100, ctrlKey: true })
  fireEvent(surface(), zoom)
  expect(zoom.defaultPrevented).toBe(true)
  expect(touch('touchstart', 160, 180, surface(), 2).defaultPrevented).toBe(true)
  expect(touch('touchmove', 170, 200, surface(), 2).defaultPrevented).toBe(true)
  touch('touchend', 170, 200); settle()
  touch('touchstart', 10); touch('touchmove', 30, 240); touch('touchend', 180, 260); settle()
  swipe(document.querySelector('input')); settle()
  touch('touchstart', 10); touch('touchmove', 30); touch('touchend', 40); settle()
  touch('touchstart', 10); touch('touchmove', 160, 180, surface(), 2); touch('touchend', 180); settle()
  const drawer = document.createElement('nav'); drawer.className = 'sidebar mobile-open'; document.body.append(drawer)
  swipe(); settle(); drawer.remove()
  expect(back).not.toHaveBeenCalled()
  expect(surface().style.transform).toBe('')
})

it('suppresses a tap generated by the end of a horizontal swipe', () => {
  render(<Harness onBack={() => {}} />)
  swipe()
  const event = new MouseEvent('click', { bubbles: true, cancelable: true })
  surface().dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
  settle()
})

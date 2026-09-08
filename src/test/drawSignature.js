import { fireEvent } from '@testing-library/react'

export function drawSignature(svg) {
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 600, height: 200 })
  const event = (type, x, y) => {
    const input = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y, button: 0 })
    Object.defineProperties(input, { pointerId: { value: 1 }, pointerType: { value: 'mouse' }, isPrimary: { value: true } })
    fireEvent(svg, input)
  }
  event('pointerdown', 30, 70); event('pointermove', 80, 120); event('pointermove', 130, 40); event('pointerup', 210, 110)
}

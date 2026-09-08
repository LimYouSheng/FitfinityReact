import { useRef } from 'react'
import { SIGNATURE_WIDTH, SIGNATURE_HEIGHT, signaturePath } from '../app/signature.js'

export function SignaturePreview({ strokes, label = 'Saved client signature' }) {
  return <svg className="signature-preview" viewBox={`0 0 ${SIGNATURE_WIDTH} ${SIGNATURE_HEIGHT}`} role="img" aria-label={label}>{strokes.map((stroke, index) => <path key={index} d={signaturePath(stroke)} />)}</svg>
}

export default function SignaturePad({ strokes, onChange, disabled = false }) {
  const current = useRef(null)
  const point = event => {
    const rect = event.currentTarget.getBoundingClientRect()
    return { x: Math.max(0, Math.min(SIGNATURE_WIDTH, (event.clientX - rect.left) / rect.width * SIGNATURE_WIDTH)), y: Math.max(0, Math.min(SIGNATURE_HEIGHT, (event.clientY - rect.top) / rect.height * SIGNATURE_HEIGHT)) }
  }
  const finish = event => {
    if (!current.current || event.pointerId !== current.current.pointerId) return
    event.stopPropagation()
    current.current = null
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
  }
  return <div className="signature-field" data-no-swipe>
    <span>Client signature</span>
    <svg className="signature-pad" viewBox={`0 0 ${SIGNATURE_WIDTH} ${SIGNATURE_HEIGHT}`} role="img" aria-label="Draw client signature" aria-disabled={disabled}
      onPointerDown={event => {
        if (disabled || !event.isPrimary || (event.pointerType === 'mouse' && event.button !== 0) || strokes.length >= 100) return
        event.preventDefault(); event.stopPropagation()
        event.currentTarget.setPointerCapture?.(event.pointerId)
        const next = [...strokes, [point(event)]]
        current.current = { pointerId: event.pointerId, strokes: next }
        onChange(next)
      }}
      onPointerMove={event => {
        const drawing = current.current
        if (!drawing || disabled || drawing.pointerId !== event.pointerId) return
        event.preventDefault(); event.stopPropagation()
        if (drawing.strokes.flat().length >= 10000) return
        const next = [...drawing.strokes.slice(0, -1), [...drawing.strokes.at(-1), point(event)]]
        current.current = { ...drawing, strokes: next }; onChange(next)
      }} onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={() => { current.current = null }}>
      {strokes.map((stroke, index) => <path key={index} d={signaturePath(stroke)} />)}
    </svg>
    <div className="inline-actions"><button type="button" className="secondary-button" disabled={disabled || !strokes.length} onClick={() => { current.current = null; onChange([]) }}>Clear Signature</button></div>
  </div>
}

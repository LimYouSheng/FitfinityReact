import { useId, useRef, useState } from 'react'
import FieldPopover from './FieldPopover.jsx'

/** Editable choices share the same menu while continuing to accept a new custom value. */
export default function SuggestionField({ options, onChange, ...props }) {
  const ref = useRef(null)
  const id = useId()
  const [open, setOpen] = useState(false)
  const matches = options.filter(option => option.toLowerCase().includes(String(props.value ?? '').toLowerCase()))
  const select = value => { onChange({ target: { value }, currentTarget: { value } }); ref.current?.focus({ preventScroll: true }); setOpen(false) }
  return <span className="suggestion-field">
    <input {...props} ref={ref} autoComplete="off" role="combobox" aria-autocomplete="list" aria-expanded={open && matches.length > 0}
      aria-controls={open && matches.length ? id : undefined}
      onFocus={() => setOpen(true)} onChange={event => { onChange(event); setOpen(true) }}
      onKeyDown={event => {
        if (event.key === 'Escape' || event.key === 'Tab') setOpen(false)
        if (event.key === 'ArrowDown' && matches.length) { event.preventDefault(); setOpen(true); requestAnimationFrame(() => document.getElementById(`${id}-0`)?.focus()) }
      }} />
    {open && matches.length > 0 && <FieldPopover anchorRef={ref} onClose={() => setOpen(false)} role="listbox" id={id} aria-label={`${props['aria-label'] ?? 'Field'} suggestions`}>
      {matches.map((option, index) => <button key={option} id={`${id}-${index}`} role="option" aria-selected={props.value === option} type="button"
        onPointerDown={event => event.preventDefault()} onClick={() => select(option)}>{option}</button>)}
    </FieldPopover>}
  </span>
}

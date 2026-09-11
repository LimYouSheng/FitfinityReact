import { useEffect, useId, useRef, useState } from 'react'
import FieldPopover from './FieldPopover.jsx'

/** Preserve native form semantics while all pointer/keyboard opening uses the app's compact menu. */
export default function SelectField({ children, onChange, ...props }) {
  const ref = useRef(null)
  const id = useId()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  useEffect(() => {
    if (open) document.getElementById(`${id}-${active}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [active, id, open])
  const options = open ? [...(ref.current?.options ?? [])] : []
  const openMenu = event => {
    event.preventDefault()
    if (ref.current?.matches(':disabled')) return
    ref.current?.focus({ preventScroll: true })
    const items = [...ref.current.options]
    const selected = ref.current.selectedIndex
    setActive(items[selected] && !items[selected].disabled && !items[selected].hidden
      ? selected : items.findIndex(option => !option.disabled && !option.hidden))
    setOpen(true)
  }
  const choose = index => {
    const option = ref.current.options[index]
    if (!option || option.disabled || option.hidden) return
    ref.current.value = option.value
    ref.current.dispatchEvent(new Event('change', { bubbles: true }))
    setOpen(false)
    ref.current.focus({ preventScroll: true })
  }
  const keyboard = event => {
    if (event.key === 'Tab') { setOpen(false); return }
    if (event.key === 'Escape') { setOpen(false); return }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) {
      event.preventDefault()
      if (!open) { openMenu(event); return }
      if (event.key === 'Enter' || event.key === ' ') { choose(active); return }
      const items = [...ref.current.options]
      const direction = event.key === 'ArrowUp' || event.key === 'End' ? -1 : 1
      let next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : active + direction
      while (items[next] && (items[next].disabled || items[next].hidden)) next += direction
      if (items[next]) setActive(next)
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault()
      if (!open) openMenu(event)
      const index = [...ref.current.options].findIndex(option => !option.disabled && !option.hidden && option.text.toLowerCase().startsWith(event.key.toLowerCase()))
      if (index >= 0) setActive(index)
    }
  }
  return <span className="select-field">
    <select {...props} ref={ref} onChange={onChange} aria-expanded={open} aria-controls={open ? id : undefined}
      aria-activedescendant={open && active >= 0 ? `${id}-${active}` : undefined}
      onPointerDown={openMenu} onMouseDown={event => event.preventDefault()} onClick={openMenu} onKeyDown={keyboard}>
      {children}
    </select>
    <span className="select-field-chevron" aria-hidden="true">⌄</span>
    {open && <FieldPopover anchorRef={ref} onClose={() => setOpen(false)} role="listbox" id={id} aria-label={props['aria-label'] ?? 'Choose an option'}>
      {options.map((option, index) => !option.hidden && <button key={`${index}-${option.value}`} id={`${id}-${index}`} type="button" role="option"
        aria-selected={String(props.value ?? '') === option.value} disabled={option.disabled} tabIndex={-1}
        className={active === index ? 'is-highlighted' : ''}
        onPointerDown={event => event.preventDefault()} onClick={() => choose(index)}>{option.text}</button>)}
    </FieldPopover>}
  </span>
}

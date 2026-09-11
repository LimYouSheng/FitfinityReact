import { useEffect, useId, useRef, useState } from 'react'
import { formatDate } from '../utils/date.js'
import FieldPopover from './FieldPopover.jsx'
import SelectField from './SelectField.jsx'

const iso = date => date.toISOString().slice(0, 10)
const months = Array.from({ length: 12 }, (_, month) => new Intl.DateTimeFormat('en-SG', { month: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(2000, month, 1))))
const weekdays = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

/** ISO values remain the form contract; the compact calendar replaces OS date-picker sheets. */
export default function DateField({ value = '', onChange, min, max, ...props }) {
  const ref = useRef(null)
  const openedWithKeyboard = useRef(false)
  const id = useId()
  const [open, setOpen] = useState(false)
  const [month, setMonth] = useState('')
  useEffect(() => {
    if (!open || !openedWithKeyboard.current) return
    const calendar = document.getElementById(id)
    const selected = calendar?.querySelector('.date-calendar-grid>button[aria-pressed="true"]:not(:disabled)')
    ;(selected ?? calendar?.querySelector('.date-calendar-grid>button:not(:disabled)'))?.focus({ preventScroll: true })
  }, [id, open])
  const show = event => {
    event.preventDefault()
    if (ref.current?.matches(':disabled')) return
    openedWithKeyboard.current = event.type === 'keydown'
    const parsed = new Date(`${value}T00:00:00Z`)
    const valid = /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(parsed.getTime()) && iso(parsed) === value
    const initial = valid ? value : min || new Date().toISOString().slice(0, 10)
    const candidate = min && initial < min ? min : max && initial > max ? max : initial
    setMonth(candidate.slice(0, 7))
    setOpen(true)
  }
  const select = next => {
    onChange?.({ target: { value: next, name: props.name }, currentTarget: { value: next, name: props.name } })
    setOpen(false)
    if (openedWithKeyboard.current) ref.current?.focus({ preventScroll: true })
  }
  const [year, monthNumber] = (month || '2000-01').split('-').map(Number)
  const offset = new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay()
  const days = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate()
  const minimumYear = min ? Number(min.slice(0, 4)) : Math.min(1900, year)
  const maximumYear = max ? Number(max.slice(0, 4)) : Math.max(new Date().getFullYear() + 10, year)
  const changeMonth = delta => setMonth(iso(new Date(Date.UTC(year, monthNumber - 1 + delta, 1))).slice(0, 7))
  return <span className="date-field">
    <input {...props} ref={ref} value={value} type="text" inputMode="numeric" placeholder={props.placeholder ?? 'YYYY-MM-DD'}
      maxLength={10} pattern="[0-9]{4}-[0-9]{2}-[0-9]{2}" min={min} max={max} onChange={onChange}
      aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined}
      onPointerDown={show} onClick={show} onKeyDown={event => { if (event.key === 'Enter' || event.key === 'ArrowDown') show(event) }} />
    {open && <FieldPopover anchorRef={ref} onClose={() => setOpen(false)} width={310} role="dialog" id={id} aria-label={`${props['aria-label'] ?? 'Date'} calendar`} className="date-calendar">
      <div className="date-calendar-heading">
        <button type="button" aria-label="Previous month" onClick={() => changeMonth(-1)} disabled={Boolean(min && month <= min.slice(0, 7))}>‹</button>
        <SelectField aria-label="Calendar picker month" value={monthNumber} onChange={event => setMonth(`${year}-${String(event.target.value).padStart(2, '0')}`)}>
          {months.map((label, index) => <option key={label} value={index + 1}>{label}</option>)}
        </SelectField>
        <SelectField aria-label="Calendar picker year" value={year} onChange={event => setMonth(`${event.target.value}-${String(monthNumber).padStart(2, '0')}`)}>
          {Array.from({ length: Math.max(1, maximumYear - minimumYear + 1) }, (_, index) => <option key={minimumYear + index}>{minimumYear + index}</option>)}
        </SelectField>
        <button type="button" aria-label="Next month" onClick={() => changeMonth(1)} disabled={Boolean(max && month >= max.slice(0, 7))}>›</button>
      </div>
      <div className="date-calendar-grid">
        {weekdays.map(day => <span key={day} aria-hidden="true">{day}</span>)}
        {Array.from({ length: offset }, (_, index) => <span key={`empty-${index}`} />)}
        {Array.from({ length: days }, (_, index) => {
          const date = `${month}-${String(index + 1).padStart(2, '0')}`
          return <button type="button" key={date} aria-label={formatDate(date)} aria-pressed={date === value}
            disabled={Boolean((min && date < min) || (max && date > max))} onClick={() => select(date)}>{index + 1}</button>
        })}
      </div>
      <div className="date-calendar-actions"><button type="button" onClick={() => select('')}>Clear</button><button type="button" onClick={() => { setOpen(false); if (openedWithKeyboard.current) ref.current?.focus({ preventScroll: true }) }}>Close</button></div>
    </FieldPopover>}
  </span>
}

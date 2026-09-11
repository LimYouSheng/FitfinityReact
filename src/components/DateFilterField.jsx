import DateField from './DateField.jsx'
import { formatDate } from '../utils/date.js'

export default function DateFilterField({
  label,
  hint,
  ariaLabel,
  value,
  min,
  max,
  onChange,
}) {
  return (
    <label className="filter-field">
      <span className="filter-label">{label}</span>
      <span className={`date-filter-control ${value ? 'has-value' : ''}`}>
        <span className="date-filter-display" aria-hidden="true">
          <span className={value ? 'date-filter-value' : 'date-filter-hint'}>
            {value ? formatDate(value) : hint}
          </span>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 3.5v3M18 3.5v3M4.5 9h15M5 5.5h14a1 1 0 0 1 1 1V20H4V6.5a1 1 0 0 1 1-1Z" />
          </svg>
        </span>
        <DateField
          aria-label={ariaLabel}

          value={value}
          min={min || undefined}
          max={max || undefined}
          onChange={event => onChange(event.target.value)}
        />
      </span>
    </label>
  )
}

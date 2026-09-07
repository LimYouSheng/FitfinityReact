import Field from './OnboardingField.jsx'
import { DAYS } from '../app/availability.js'

/** The single multi-day/time-block editor; the owning feature controls the draft. */
export default function AvailabilityEditor({
  blocks, selectedDays, from, to, error, listLabel,
  onToggleDay, onFrom, onTo, onAdd, onRemove, onReset,
}) {
  return (
    <div className="onboarding-availability">
      <Field label="Possible days" required group error={error}>
        <div className="onboarding-day-grid" aria-label="Possible days">
          {DAYS.map(day => (
            <button key={day} type="button" aria-label={day}
              aria-pressed={selectedDays.includes(day)}
              className={selectedDays.includes(day) ? 'selected' : ''}
              onClick={() => onToggleDay(day)}>{day.slice(0, 3)}</button>
          ))}
        </div>
      </Field>
      <div className="onboarding-time-row">
        <Field label="From" required><input aria-label="Availability from" type="time" value={from} onChange={event => onFrom(event.target.value)} /></Field>
        <Field label="To" required><input aria-label="Availability to" type="time" value={to} onChange={event => onTo(event.target.value)} /></Field>
        <button type="button" className="onboarding-button primary" onClick={onAdd}>Add Time</button>
      </div>
      {blocks.length > 0 ? (
        <div className="onboarding-preference-list" aria-label={listLabel}>
          {blocks.map(item => (
            <div className="onboarding-preference-row" key={item.id}>
              <div><strong>{item.days.join(', ')}</strong><span>{item.from}–{item.to}</span></div>
              <button type="button" className="onboarding-button"
                aria-label={`Remove ${item.days.join(', ')} ${item.from}–${item.to}`}
                onClick={() => onRemove(item.id)}>Remove</button>
            </div>
          ))}
        </div>
      ) : <p className="onboarding-hint">No availability blocks added yet.</p>}
      <button type="button" className="onboarding-button" onClick={onReset}>Reset Availability</button>
    </div>
  )
}

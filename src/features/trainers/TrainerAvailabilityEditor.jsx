import { useRef, useState } from 'react'
import AvailabilityEditor from '../../components/AvailabilityEditor.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { availabilityBlockError } from '../../app/availability.js'
import { availabilityBlocks, validateAvailability } from '../../app/scheduleChanges.js'

export default function TrainerAvailabilityEditor({ policy, availability, approvalNeeded, onSave, onCancel }) {
  const confirm = useActionConfirmation()
  const [blocks, setBlocks] = useState(() => availabilityBlocks(availability))
  const [days, setDays] = useState([])
  const [from, setFrom] = useState(policy.availability.from)
  const [to, setTo] = useState(policy.availability.to)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const locked = useRef(false)
  const reset = () => { setBlocks([]); setDays([]); setFrom(policy.availability.from); setTo(policy.availability.to); setError('') }
  const save = async () => {
    if (locked.current) return
    locked.current = true
    setBusy(true)
    setError('')
    try {
      if (days.length) throw new Error('Add the selected days with Add Time, or deselect them before saving.')
      validateAvailability(blocks)
      if (await confirm({ title: approvalNeeded ? 'Request availability change?' : 'Save availability?',
        message: `${blocks.length ? 'Save these availability blocks?' : 'Set every day to unavailable?'} Existing booked sessions keep their dates and times.`,
        confirmLabel: approvalNeeded ? 'Send Request' : 'Save Availability' })) {
        await onSave(blocks)
      }
    } catch (failure) { setError(failure.message) }
    finally { locked.current = false; setBusy(false) }
  }
  return <>
    <div className="section-head">
      <h2>Edit Availability</h2>
      <div className="inline-actions">
        <button type="button" className="text-action muted-action" disabled={busy} onClick={onCancel}>Cancel</button>
        <button type="button" className="text-action" disabled={busy} onClick={save}>{approvalNeeded ? 'Send Request' : 'Save'}</button>
      </div>
    </div>
    <fieldset className="availability-editor-fields" disabled={busy}>
      <AvailabilityEditor blocks={blocks} selectedDays={days} from={from} to={to} error={error} listLabel="Proposed availability"
        onToggleDay={day => setDays(current => current.includes(day) ? current.filter(item => item !== day) : [...current, day])}
        onFrom={setFrom} onTo={setTo} onReset={reset}
        onRemove={id => setBlocks(current => current.filter(item => item.id !== id))}
        onAdd={() => {
          const block = { id: `availability-${Date.now()}-${Math.random().toString(36).slice(2)}`, days, from, to }
          const problem = availabilityBlockError(block, blocks, true)
          setError(problem)
          if (!problem) { setBlocks(current => [...current, block]); setDays([]) }
        }} />
    </fieldset>
    {error && <p role="alert" className="onboarding-error">{error}</p>}
  </>
}

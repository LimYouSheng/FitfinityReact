import { useState } from 'react'

export default function FixedWeeklySchedule({ slots, editable, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(slots)
  const begin = () => { setDraft(slots.map(slot => ({ ...slot }))); setEditing(true) }
  const cancel = () => { setDraft(slots); setEditing(false) }
  const save = () => { onSave(draft); setEditing(false) }
  return (
    <section className="panel schedule-panel">
      <div className="section-head"><h2>Fixed Weekly Schedule</h2>{editable && (!editing ? <button type="button" className="text-action" onClick={begin}>Edit</button> : <div className="inline-actions"><button type="button" className="text-action muted-action" onClick={cancel}>Cancel</button><button type="button" className="text-action" onClick={save}>Save</button></div>)}</div>
      <div className="schedule-list">
        {draft.map((slot, index) => <div className="schedule-row" key={slot.id}>
          <span>{slot.day}</span>
          {editing ? <div className="time-fields"><input aria-label={`${slot.day} from`} type="time" value={slot.from} onChange={event => setDraft(current => current.map((item, i) => i === index ? { ...item, from: event.target.value } : item))} /><input aria-label={`${slot.day} to`} type="time" value={slot.to} onChange={event => setDraft(current => current.map((item, i) => i === index ? { ...item, to: event.target.value } : item))} /></div> : <strong>{slot.from}–{slot.to}</strong>}
        </div>)}
      </div>
    </section>
  )
}

import { useEffect, useState } from 'react'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'

function cloneSlots(slots) {
  return (slots ?? []).map(slot => ({ ...slot }))
}

export default function FixedWeeklySchedule({
  slots,
  editable,
  editing,
  editDisabled,
  onBeginEdit,
  onEndEdit,
  onSave,
}) {
  const confirmAction = useActionConfirmation()
  const [draft, setDraft] = useState(() => cloneSlots(slots))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!editing) setDraft(cloneSlots(slots))
  }, [slots, editing])

  const begin = () => {
    setError('')
    setDraft(cloneSlots(slots))
    onBeginEdit()
  }

  const cancel = () => {
    setDraft(cloneSlots(slots))
    onEndEdit()
  }

  const save = async () => {
    const confirmed = await confirmAction({
      title: 'Save fixed weekly schedule?',
      message: 'This will update the weekly times and all upcoming sessions, or send the change for owner approval when required.',
      confirmLabel: 'Save Schedule',
    })
    if (!confirmed) return

    setError('')
    setSaving(true)

    try {
      const result = await onSave(draft)

      if (result?.outcome === 'requested') {
        setDraft(cloneSlots(slots))
      }

      onEndEdit()
    } catch (failure) {
      setError(failure.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={`panel schedule-panel ${editing ? 'editing-section' : ''}`}>
      <div className="section-head">
        <h2>Fixed Weekly Schedule</h2>

        {editable && (!editing ? (
          <button type="button" className="text-action" disabled={editDisabled} onClick={begin}>Edit</button>
        ) : (
          <div className="inline-actions">
            <button
              type="button"
              className="text-action muted-action"
              disabled={saving}
              onClick={cancel}
            >
              Cancel
            </button>

            <button
              type="button"
              className="text-action"
              disabled={saving}
              onClick={save}
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        ))}
      </div>

      {error && <p role="alert" className="onboarding-error">{error}</p>}
      <div className="schedule-list">
        {draft.map((slot, index) => (
          <div className="schedule-row" key={slot.id}>
            <span>{slot.day}</span>

            {editing ? (
              <div className="time-fields">
                <input
                  aria-label={`${slot.day} from`}
                  type="time"
                  value={slot.from}
                  onChange={event =>
                    setDraft(current =>
                      current.map((item, i) =>
                        i === index
                          ? { ...item, from: event.target.value }
                          : item
                      )
                    )
                  }
                />

                <input
                  aria-label={`${slot.day} to`}
                  type="time"
                  value={slot.to}
                  onChange={event =>
                    setDraft(current =>
                      current.map((item, i) =>
                        i === index
                          ? { ...item, to: event.target.value }
                          : item
                      )
                    )
                  }
                />
              </div>
            ) : (
              <strong>{slot.from}–{slot.to}</strong>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}

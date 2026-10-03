import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import DateField from '../../components/DateField.jsx'
import SelectField from '../../components/SelectField.jsx'
import { formatDate } from '../../utils/date.js'

export default function SessionChangeDialogs({ schedule, saving, detailsError, setDetailsError, replacementTrainers }) {
  const { requestKind, setRequestKind, timeRequestDraft, setTimeRequestDraft, trainerRequestId, setTrainerRequestId, clock, timeRequestError, validSchedule, submitTimeRequest, submitTrainerRequest } = schedule

  return (
    <>
          <ConfirmDialog open={requestKind === 'postpone'} title="Postpone this session?"
            confirmLabel={saving ? 'Checking…' : schedule.lastSlotChanged || schedule.postponementConflicts.length ? 'Check Availability' : 'Confirm Postponement'}
            confirmDisabled={saving || !schedule.postponement || Boolean(schedule.lastSlotChanged && !validSchedule(schedule.lastSlotDraft)) || Boolean(schedule.postponementConflicts.length && !schedule.lastSlotChanged)}
            onCancel={() => { if (!saving) { setRequestKind(null); setDetailsError('') } }} onConfirm={schedule.submitPostponement}>
            <p>The suggested slot is one week after the current package’s last session. Only this session moves; other bookings stay unchanged. Credits stay the same.</p>
            <table className="postponement-preview"><thead><tr><th>Current slot</th><th>New slot</th></tr></thead><tbody>
              {schedule.postponement?.changes.map(change => <tr key={change.sessionId}><td>{formatDate(change.before.date)}<br />{change.before.from}–{change.before.to}</td><td>{formatDate(change.next.date)}<br />{change.next.from}–{change.next.to}</td></tr>)}
            </tbody></table>
            {schedule.lastSlotChanged && <p role="status">Check availability to update this preview.</p>}
            {schedule.postponementConflicts.map(conflict => <p key={conflict.sessionId} role="alert" className="validation-copy">{conflict.message}</p>)}
            {schedule.editingLastSlot ? <fieldset className="session-request-fields" disabled={saving}>
              <legend>Choose another slot</legend>
              <label>Date<DateField aria-label="Postponed session date" min={schedule.postponement?.lastBooking?.date} value={schedule.lastSlotDraft?.date ?? ''} onChange={event => { setDetailsError(''); schedule.setLastSlotDraft(current => ({ ...current, date: event.target.value })) }} /></label>
              <label>From<input aria-label="Postponed session start time" type="time" value={schedule.lastSlotDraft?.from ?? ''} onChange={event => { setDetailsError(''); schedule.setLastSlotDraft(current => ({ ...current, from: event.target.value })) }} /></label>
              <label>To<input aria-label="Postponed session end time" type="time" value={schedule.lastSlotDraft?.to ?? ''} onChange={event => { setDetailsError(''); schedule.setLastSlotDraft(current => ({ ...current, to: event.target.value })) }} /></label>
            </fieldset> : <button type="button" className="secondary-button small" disabled={saving} onClick={() => schedule.setEditingLastSlot(true)}>Change proposed slot</button>}
            {detailsError && <p role="alert" className="validation-copy">{detailsError}</p>}
          </ConfirmDialog>
          <ConfirmDialog
            open={requestKind === 'time'}
            title="Request Time Change"
            confirmLabel={saving ? 'Submitting…' : 'Review Request'}
            confirmDisabled={saving || !validSchedule(timeRequestDraft) || Boolean(timeRequestError)}
            onCancel={() => {
              setRequestKind(null)
              setDetailsError('')
            }}
            onConfirm={submitTimeRequest}
          >
            <div className="session-request-fields">
              <label>Date<DateField aria-label="Requested session date"  min={clock.date} value={timeRequestDraft.date} onChange={event => { setDetailsError(''); setTimeRequestDraft(current => ({ ...current, date: event.target.value })) }} /></label>
              <label>From<input aria-label="Requested start time" type="time" min={timeRequestDraft.date === clock.date ? clock.time : undefined} value={timeRequestDraft.from} onChange={event => { setDetailsError(''); setTimeRequestDraft(current => ({ ...current, from: event.target.value })) }} /></label>
              <label>To<input aria-label="Requested end time" type="time" value={timeRequestDraft.to} onChange={event => setTimeRequestDraft(current => ({ ...current, to: event.target.value }))} /></label>
            </div>
            {(detailsError || timeRequestError) && <p className="validation-copy" role="alert">{detailsError || timeRequestError}</p>}
          </ConfirmDialog>

          <ConfirmDialog
            open={requestKind === 'trainer'}
            title="Request Trainer Change"
            confirmLabel={saving ? 'Submitting…' : 'Review Request'}
            confirmDisabled={saving || !trainerRequestId}
            onCancel={() => {
              setRequestKind(null)
              setDetailsError('')
            }}
            onConfirm={submitTrainerRequest}
          >
            <label className="session-request-trainer">
              Replacement trainer
              <SelectField aria-label="Requested replacement trainer" value={trainerRequestId} onChange={event => setTrainerRequestId(event.target.value)}>
                <option value="">Choose trainer</option>
                {replacementTrainers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
              </SelectField>
            </label>
            {detailsError && <p className="validation-copy" role="alert">{detailsError}</p>}
          </ConfirmDialog>
    </>
  )
}

import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import DateField from '../../components/DateField.jsx'
import SelectField from '../../components/SelectField.jsx'
import { formatDate } from '../../utils/date.js'

export default function SessionChangeDialogs({ schedule, saving, detailsError, setDetailsError, replacementTrainers }) {
  const { requestKind, setRequestKind, timeRequestDraft, setTimeRequestDraft, trainerRequestId, setTrainerRequestId, clock, timeRequestError, validSchedule, submitTimeRequest, submitTrainerRequest } = schedule

  return (
    <>
          <ConfirmDialog open={requestKind === 'postpone'} title="Postpone this session?"
            confirmLabel={saving ? 'Saving…' : 'Confirm Postponement'} confirmDisabled={saving || !schedule.postponement}
            onCancel={() => { if (!saving) { setRequestKind(null); setDetailsError('') } }} onConfirm={schedule.submitPostponement}>
            <p>When applied, this session becomes open with date/time not set. Its old booking is released. Other bookings, package credits and validity stay unchanged. Dated sessions are renumbered chronologically.</p>
            <table className="postponement-preview"><thead><tr><th>Current slot</th><th>New state</th></tr></thead><tbody>
              {schedule.postponement?.changes.map(change => <tr key={change.sessionId}><td>{formatDate(change.before.date)}<br />{change.before.from}–{change.before.to}</td><td>Open session · Date/time not set</td></tr>)}
            </tbody></table>
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

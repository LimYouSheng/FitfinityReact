import { useMemo, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import SelectField from '../../components/SelectField.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import { remainingTrainerSessions } from '../../app/status.js'
import { availableReplacementTrainers } from '../../app/bookingAvailability.js'
import { formatDate } from '../../utils/date.js'
import { formatTime } from './trainerTime.js'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'

export default function TrainerDeactivationDialog({ trainer, trainers, clients, sessions, deactivateOpen, setDeactivateOpen, onDeactivate, reviewed, initialReplacements = {}, uncertain = false, onPreview }) {
  const { guardNavigation } = useEditGuard()
  const [replacements, setReplacements] = useState(initialReplacements)
  const [view, setView] = useState(reviewed)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const remaining = useMemo(
    () => view ? view.sessions.map(row => ({ ...row, from: row.startsAt, to: row.endsAt })) : remainingTrainerSessions(trainer.id, sessions, clients),
    [trainer.id, sessions, clients, view]
  )
  const remainingPagination = usePagination(remaining, `${trainer.id}|${deactivateOpen}`, 'trainer.reassignmentPage')

  const replacementOptions = new Map(remaining.map(session => [session.id,
    view ? session.choices.filter(t => !t.error) : availableReplacementTrainers({ trainers, clients, sessions }, session, replacements)]))
  const allAssigned = remaining.every(session => replacementOptions.get(session.id).some(item => item.id === replacements[session.id]))

  return (
    <ConfirmDialog
      open={deactivateOpen}
      title={`Deactivate ${trainer.name}?`}
      confirmLabel={busy ? 'Checking…' : uncertain ? 'Check Deactivation' : 'Deactivate Trainer'}
      danger
      confirmDisabled={!allAssigned || busy || Boolean(error && !uncertain)}
      onCancel={() => {
        if (busy) return
        const close = () => { setDeactivateOpen(false); setReplacements({}) }
        if (view) guardNavigation(close)
        else close()
      }}
      onConfirm={async () => {
        if (busy) return
        setBusy(true); setError('')
        try {
          await onDeactivate(replacements, view)
          setDeactivateOpen(false)
          setReplacements({})
        } catch (failure) { if (view) setError(failure.message) }
        finally { setBusy(false) }
      }}
    >
      <p>
        An inactive trainer will immediately stop appearing in active trainer lists and availability matching.
        Any remaining tagged sessions must be reassigned first.
      </p>

      {remaining.length > 0 ? (
        <div className="reassign-list">
          {remainingPagination.items.map(session => {
            const client = view ? { name: session.clientName } : clients.find(item => item.id === session.clientId)
            const selectableReplacements = replacementOptions.get(session.id)
            return (
              <div className="reassign-row" key={session.id}>
                <div>
                  <strong>{client?.name ?? 'Client'}</strong>
                  <span>{session.scheduleState === 'open' ? 'Open session' : `${formatDate(session.date)} • ${formatTime(session.from)}–${formatTime(session.to)}`}</span>
                </div>
                <label>
                  <span>Reassign to</span>
                  <SelectField
                    aria-label={`Reassign ${client?.name ?? session.id}`}
                    value={selectableReplacements.some(item => item.id === replacements[session.id]) ? replacements[session.id] : ''}
                    disabled={!selectableReplacements.length || busy || uncertain}
                    onChange={async event => {
                      const next = { ...replacements }
                      if (event.target.value) next[session.id] = event.target.value
                      else delete next[session.id]
                      setReplacements(next); setError('')
                      if (onPreview) {
                        setBusy(true)
                        try { setView(await onPreview({ reviewed: view, replacements: next })) }
                        catch (failure) { setError(failure.message) }
                        finally { setBusy(false) }
                      }
                    }}
                  >
                    <option value="">{selectableReplacements.length ? 'Choose available trainer' : 'No trainer available'}</option>
                    {selectableReplacements.map(item => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </SelectField>
                  {!selectableReplacements.length && <span>No active trainer is free for this session. Resolve the booking conflict before deactivation.</span>}
                </label>
              </div>
            )
          })}
          <PaginationControls {...remainingPagination} onPage={remainingPagination.setPage} />
        </div>
      ) : (
        <div className="notice">No remaining sessions are tagged to this trainer.</div>
      )}

      {!allAssigned && <p className="validation-copy">Choose an available replacement for every remaining session.</p>}
      {error && <p role="alert">{error}</p>}
    </ConfirmDialog>
  )
}

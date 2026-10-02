import { useMemo, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import SelectField from '../../components/SelectField.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import { remainingTrainerSessions } from '../../app/status.js'
import { availableReplacementTrainers } from '../../app/bookingAvailability.js'
import { formatDate } from '../../utils/date.js'
import { formatTime } from './trainerTime.js'

export default function TrainerDeactivationDialog({ trainer, trainers, clients, sessions, deactivateOpen, setDeactivateOpen, onDeactivate }) {
  const [replacements, setReplacements] = useState({})
  const remaining = useMemo(
    () => remainingTrainerSessions(trainer.id, sessions, clients),
    [trainer.id, sessions, clients]
  )
  const remainingPagination = usePagination(remaining, `${trainer.id}|${deactivateOpen}`, 'trainer.reassignmentPage')

  const replacementOptions = new Map(remaining.map(session => [session.id,
    availableReplacementTrainers({ trainers, clients, sessions }, session, replacements)]))
  const allAssigned = remaining.every(session => replacementOptions.get(session.id).some(item => item.id === replacements[session.id]))

  return (
    <ConfirmDialog
      open={deactivateOpen}
      title={`Deactivate ${trainer.name}?`}
      confirmLabel="Deactivate Trainer"
      danger
      confirmDisabled={!allAssigned}
      onCancel={() => {
        setDeactivateOpen(false)
        setReplacements({})
      }}
      onConfirm={async () => {
        try {
          await onDeactivate(replacements)
          setDeactivateOpen(false)
          setReplacements({})
        } catch { /* Failure is shown in the action banner; keep the dialog open. */ }
      }}
    >
      <p>
        An inactive trainer will immediately stop appearing in active trainer lists and availability matching.
        Any remaining tagged sessions must be reassigned first.
      </p>

      {remaining.length > 0 ? (
        <div className="reassign-list">
          {remainingPagination.items.map(session => {
            const client = clients.find(item => item.id === session.clientId)
            const selectableReplacements = replacementOptions.get(session.id)
            return (
              <div className="reassign-row" key={session.id}>
                <div>
                  <strong>{client?.name ?? 'Client'}</strong>
                  <span>{formatDate(session.date)} • {formatTime(session.from)}–{formatTime(session.to)}</span>
                </div>
                <label>
                  <span>Reassign to</span>
                  <SelectField
                    aria-label={`Reassign ${client?.name ?? session.id}`}
                    value={selectableReplacements.some(item => item.id === replacements[session.id]) ? replacements[session.id] : ''}
                    disabled={!selectableReplacements.length}
                    onChange={event => setReplacements(current => ({
                      ...current,
                      [session.id]: event.target.value,
                    }))}
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
    </ConfirmDialog>
  )
}

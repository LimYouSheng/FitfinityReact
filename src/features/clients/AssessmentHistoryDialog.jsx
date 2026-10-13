import { useEffect, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import { formatDate, formatTimestamp } from '../../utils/date.js'
import { AssessmentDialog } from './ClientAssessments.jsx'

export default function AssessmentHistoryDialog({ definition, person, services, onClose, timeZone }) {
  const [assessmentId, setAssessmentId] = useState(null)
  const [offset, setOffset] = useState(0)
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState(null)
  const [selected, setSelected] = useState(null)
  const key = JSON.stringify([person.id, definition.id, assessmentId, offset, attempt])
  useEffect(() => {
    let current = true
    services.readAssessmentHistory({ personId: person.id, formId: definition.id, assessmentId, offset })
      .then(value => { if (current) setResult({ key, value }) })
      .catch(error => { if (current) setResult({ key, error }) })
    return () => { current = false }
  }, [services, person.id, definition.id, assessmentId, offset, key])
  const ready = result?.key === key ? result : null
  if (selected) return <AssessmentDialog definition={definition} person={{ ...person, name: selected.clientName, birthday: selected.clientBirthday }}
    record={selected} readOnly timeZone={timeZone} onClose={() => setSelected(null)} />
  return <ConfirmDialog open title={`${definition.title} history`} hideConfirm cancelLabel="Back to Form" onCancel={onClose}>
    <p>{person.name} — {assessmentId ? 'Saved revisions of this occasion' : 'Assessment occasions'}</p>
    {assessmentId && <button type="button" className="secondary-button" onClick={() => { setAssessmentId(null); setOffset(0) }}>Back to Occasions</button>}
    {!ready && <p role="status">Loading assessment history…</p>}
    {ready?.error && <div role="alert"><p>{ready.error.message}</p><button type="button" onClick={() => setAttempt(value => value + 1)}>Retry History</button></div>}
    {ready?.value && <>
      {!ready.value.items.length && <p>No saved records on this page.</p>}
      <ul className="stack-gap">{ready.value.items.map(record => <li key={record.revisionId}>
        <p><strong>{formatDate(record.date)}</strong> — {record.status === 'filled' ? 'Filled' : record.status === 'draft' ? 'Draft' : 'Voided'} — Revision {record.revision}</p>
        <p>{record.actorName} · {formatTimestamp(record.savedAt, timeZone)}</p>
        {record.reason && <p>Reason: {record.reason}</p>}
        <button type="button" className="secondary-button" onClick={() => setSelected(record)}>View Saved Form</button>
        {!assessmentId && <button type="button" className="text-action" onClick={() => { setAssessmentId(record.assessmentId); setOffset(0) }}>View Revisions</button>}
      </li>)}</ul>
      <div className="inline-actions">
        <button type="button" disabled={offset === 0} onClick={() => setOffset(value => value - 25)}>Previous History Page</button>
        <button type="button" disabled={!ready.value.hasMore || offset >= 10000} onClick={() => setOffset(value => value + 25)}>Next History Page</button>
      </div>
    </>}
  </ConfirmDialog>
}

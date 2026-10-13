import { useEffect, useRef, useState } from 'react'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { AssessmentDialog } from './ClientAssessments.jsx'
import AssessmentHistoryDialog from './AssessmentHistoryDialog.jsx'

export default function AssessmentRecordDialog({ definition, person, record, businessDate, viewer, timeZone,
  editable, services, onSave, onClose, onSaved, onEditChange }) {
  const confirmAction = useActionConfirmation()
  const [review] = useState(() => ({ person: structuredClone(person), record: record ? structuredClone(record) : null, businessDate }))
  const [mode, setMode] = useState(record ? 'view' : 'edit')
  const saved = useRef(false)
  const editing = mode === 'edit' || mode === 'new'
  useEffect(() => {
    onEditChange(editing)
    return () => onEditChange(false)
  }, [editing, onEditChange])
  const close = () => { onClose(); if (saved.current) onSaved() }
  if (mode === 'history') return <AssessmentHistoryDialog definition={definition} person={review.person} services={services} timeZone={timeZone} onClose={() => setMode('view')} />
  const current = mode === 'new' ? null : review.record
  const displayPerson = !editing && current ? { ...review.person, name: current.clientName, birthday: current.clientBirthday } : review.person
  const draft = editing ? { ...(current ?? { answers: {}, date: review.businessDate }), assessor: viewer.name } : current
  const save = event => async value => {
    const assessment = { personId: review.person.id, expectedPersonVersion: review.person.version,
      formId: definition.id, formVersion: definition.version, event, record: value,
      ...(mode === 'edit' && review.record ? { assessmentId: review.record.assessmentId, expectedVersion: review.record.revision } : {}),
      ...(mode === 'new' ? { previousAssessmentId: review.record.assessmentId, expectedPreviousVersion: review.record.revision } : {}) }
    const result = await onSave(assessment)
    saved.current = true
    return result
  }
  const actions = !editing && current && <>
    {editable && !review.person.birthday && <p className="onboarding-hint">The current profile needs a date of birth before an assessment can be started or resumed. This saved form retains its original details.</p>}
    <div className="inline-actions">
    <button type="button" className="secondary-button" onClick={() => setMode('history')}>View Assessment History</button>
    {editable && review.person.birthday && current.status === 'draft' && <button type="button" className="primary-button" onClick={() => setMode('edit')}>Resume Draft</button>}
    {editable && review.person.birthday && current.status !== 'draft' && <button type="button" className="secondary-button" onClick={async () => {
      if (await confirmAction({ title: `Start a new ${definition.title} assessment?`, message: 'The previous occasion and its answers will remain in history. The new form starts blank.', confirmLabel: 'Start Reassessment' })) setMode('new')
    }}>Start Reassessment</button>}
    </div>
  </>
  return <AssessmentDialog key={mode} definition={definition} person={displayPerson} record={draft} assessor={viewer.name}
    timeZone={timeZone} readOnly={!editing} onSave={save('completed')} onSaveDraft={editing ? save('draft') : undefined}
    saveLabel="Complete Assessment" guardUncertain actions={actions} onClose={close} />
}

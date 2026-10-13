import { useEffect, useMemo, useState } from 'react'
import { managesOperations } from '../../app/permissions.js'
import usePortalActions from '../../hooks/usePortalActions.js'
import ClientAssessments from './ClientAssessments.jsx'
import AssessmentRecordDialog from './AssessmentRecordDialog.jsx'

export default function ClientAssessmentWorkspace({ client, viewer, services, generation, timeZone, disabled, onEditChange }) {
  const { runAction } = usePortalActions()
  const [result, setResult] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const [activePerson, setActivePerson] = useState(0)
  const [checking, setChecking] = useState(false)
  const source = JSON.stringify(client)
  const reviewedClient = useMemo(() => JSON.parse(source), [source])
  const editable = managesOperations(viewer) && client.status === 'active'
  useEffect(() => {
    let current = true
    services.readClientAssessments(reviewedClient)
      .then(value => { if (current) setResult({ source, generation, value }) })
      .catch(error => { if (current) setResult({ source, generation, error }) })
    return () => { current = false }
  }, [reviewedClient, source, services, generation, attempt])
  const retry = () => { setResult(null); setAttempt(value => value + 1) }
  const ready = result?.source === source && result.generation === generation ? result : null
  if (!ready) return <p role="status">Loading assessment records…</p>
  if (ready.error) return <div role="alert"><p>{ready.error.message}</p><button type="button" onClick={retry}>Retry Assessments</button></div>
  const data = ready.value
  return <>
    {editable && !data.people[activePerson]?.birthday && <p className="onboarding-hint">Add this client’s date of birth in General Information before starting or resuming an assessment.</p>}
    {data.pending && <div role="alert"><p>A previous assessment save needs checking before another form can be saved.</p>
      <button type="button" disabled={checking} onClick={async () => {
        setChecking(true)
        try { await runAction(() => services.clientService.saveAssessment(data.pending), { message: 'Assessment save confirmed.' }); retry() }
        catch { /* The action banner preserves the error and the original pending command. */ }
        finally { setChecking(false) }
      }}>{checking ? 'Checking Assessment…' : 'Check Previous Assessment Save'}</button>
    </div>}
    <ClientAssessments people={data.people} activePerson={activePerson} setActivePerson={setActivePerson} readOnly
      disabled={disabled || Boolean(data.pending)} assessor={viewer.name} timeZone={timeZone}
      hint={editable ? 'Open a saved form to view its history, resume a draft or start a reassessment. Unfilled forms can be saved as drafts or completed.' : 'Open saved forms and history. Inactive client records are read-only.'}
      canOpenForm={(person, _definition, record) => Boolean(record) || (editable && Boolean(person.birthday))}
      renderForm={context => <AssessmentRecordDialog {...context} key={`${context.person.id}-${context.definition.id}`}
        businessDate={data.businessDate} viewer={viewer} timeZone={timeZone} services={services} editable={editable}
        onEditChange={onEditChange} onSaved={retry} onSave={assessment => runAction(
          () => services.clientService.saveAssessment({ id: client.id, assessment }),
          { message: assessment.event === 'draft' ? 'Assessment draft saved.' : 'Assessment saved.' },
        )} />} />
  </>
}

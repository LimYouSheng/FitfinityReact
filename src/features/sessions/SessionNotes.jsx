import { useEffect, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { sessionDurationMinutes } from '../../app/sessionRules.js'

export default function SessionNotes({ session, outcome, displayedSummary, activeEditor, setActiveEditor, saving, setSaving, setDetailsError, canEditNotes, onSaveOutcome, onSaveClientSummary }) {
  const confirmAction = useActionConfirmation()
  const [outcomeDraft, setOutcomeDraft] = useState(outcome)
  const [summaryDraft, setSummaryDraft] = useState(displayedSummary)

  useEffect(() => {
    if (!activeEditor) {
      setOutcomeDraft(outcome)
      setSummaryDraft(displayedSummary)
    }
  }, [activeEditor, displayedSummary, outcome])

  const saveOutcome = async () => {
    const confirmed = await confirmAction({
      title: 'Save session outcome?',
      message: 'This will update the recorded duration and trainer comments for this session.',
      confirmLabel: 'Save Outcome',
    })
    if (!confirmed) return

    setSaving(true)
    try {
      await onSaveOutcome(outcomeDraft)
      setActiveEditor(null)
    } catch (failure) {
      setDetailsError(failure.message || 'Could not complete this action. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const saveSummary = async () => {
    const confirmed = await confirmAction({
      title: 'Save client-facing summary?',
      message: 'This will replace the summary prepared for sharing with the client.',
      confirmLabel: 'Save Summary',
    })
    if (!confirmed) return

    setSaving(true)
    try {
      await onSaveClientSummary(summaryDraft)
      setActiveEditor(null)
    } catch (failure) {
      setDetailsError(failure.message || 'Could not complete this action. Try again.')
    } finally {
      setSaving(false)
    }
  }


  return (
    <>
          <Panel className={`top-gap session-outcome-panel ${activeEditor === 'outcome' ? 'editing-section' : ''}`}>
            <div className="section-head">
              <h2>Session Outcome</h2>
              {activeEditor === 'outcome' ? (
                <div className="inline-actions">
                  <button type="button" className="text-action muted-action" disabled={saving} onClick={() => setActiveEditor(null)}>Cancel</button>
                  <button type="button" className="text-action" disabled={saving} onClick={saveOutcome}>{saving ? 'Saving…' : 'Save'}</button>
                </div>
              ) : canEditNotes && (
                <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => setActiveEditor('outcome')}>Edit</button>
              )}
            </div>

            {activeEditor === 'outcome' ? (
              <div className="session-outcome-editor">
                <label>
                  Duration (minutes)
                  <input type="number" readOnly value={sessionDurationMinutes(session)} />
                </label>
                <label>
                  Trainer comments
                  <textarea rows="3" value={outcomeDraft.trainerComments} onChange={event => setOutcomeDraft(current => ({ ...current, trainerComments: event.target.value }))} />
                </label>
                <div className="recorded-results"><h3>Recorded exercise results</h3>
                  {(outcomeDraft.exerciseResults ?? []).map((result, index) => <div className="recorded-result" key={result.id}><strong>{result.name}</strong>{[['loadKg', 'Load (kg)'], ['reps', 'Reps'], ['sets', 'Sets']].map(([field, label]) => <label key={field}>{label}<input aria-label={`${label} for ${result.name}`} type="number" min={field === 'loadKg' ? '0' : '1'} step={field === 'loadKg' ? '0.1' : '1'} value={result[field]} onChange={event => setOutcomeDraft(current => ({ ...current, exerciseResults: current.exerciseResults.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: event.target.value } : row) }))} /></label>)}</div>)}
                </div>
              </div>
            ) : (
              <dl className="session-outcome-list">
                <div><dt>Duration</dt><dd>{outcome.durationMinutes} minutes</dd></div>
                <div><dt>Trainer comments</dt><dd>{outcome.trainerComments || 'No comments yet.'}</dd></div>
                {(session.exerciseResults ?? []).map(result => <div key={result.id}><dt>{result.name}</dt><dd>{result.loadKg} kg · {result.reps} reps · {result.sets} sets</dd></div>)}
              </dl>
            )}
          </Panel>

          <Panel className={`top-gap client-summary-panel ${activeEditor === 'summary' ? 'editing-section' : ''}`}>
            <div className="section-head">
              <h2>Client-Facing Summary</h2>
              {activeEditor === 'summary' ? (
                <div className="inline-actions">
                  <button type="button" className="text-action muted-action" disabled={saving} onClick={() => setActiveEditor(null)}>Cancel</button>
                  <button type="button" className="text-action" disabled={saving || !summaryDraft.trim()} onClick={saveSummary}>{saving ? 'Saving…' : 'Save'}</button>
                </div>
              ) : canEditNotes && (
                <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => setActiveEditor('summary')}>Edit</button>
              )}
            </div>

            {activeEditor === 'summary' ? (
              <div className="client-summary-editor">
                <textarea rows="8" value={summaryDraft} onChange={event => setSummaryDraft(event.target.value)} />
              </div>
            ) : (
              <div className="client-summary-copy">{displayedSummary}</div>
            )}

          </Panel>

    </>
  )
}

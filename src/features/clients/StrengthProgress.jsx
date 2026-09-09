import usePageState from '../../hooks/usePageState.js'
import { useEffect, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import { PROGRESS_REPORT_ACTIONS } from '../../app/progress.js'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import { formatTimestamp } from '../../utils/date.js'
import { downloadProgressReport, progressReportFile } from './progressReport.js'
import ProgressReportShareDialog from './ProgressReportShareDialog.jsx'

import StrengthProgressChart from './StrengthProgressChart.jsx'
import { progressNumber, progressSummary, progressChange } from './progressChart.js'

export default function StrengthProgress({ client, user, timeZone, onRecordAction, onLoadHistory }) {
  const exercises = client.strengthProgress ?? []
  const [selectedId, setSelectedId] = usePageState('StrengthProgress.selectedId', exercises[0]?.id ?? '')
  const selected = exercises.find(exercise => exercise.id === selectedId) ?? exercises[0]

  const owner = user?.role === 'owner'
  const [historyOpen, setHistoryOpen] = usePageState(`client.${client.id}.reportHistoryOpen`, false)
  const [historyState, setHistoryState] = useState({ items: [], loading: false, error: '' })
  const [historyRevision, setHistoryRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [unsavedAction, setUnsavedAction] = useState(null)
  const [shareClient, setShareClient] = useState(null)
  const acting = useRef(false)
  const historyPages = usePagination(historyState.items, client.id, `client.${client.id}.reportHistoryPage`)

  useEffect(() => {
    if (!owner || !historyOpen) return
    let current = true
    setHistoryState(previous => ({ ...previous, loading: true, error: '' }))
    Promise.resolve().then(() => onLoadHistory()).then(items => {
      if (current) setHistoryState({ items, loading: false, error: '' })
    }).catch(error => {
      if (current) setHistoryState({ items: [], loading: false, error: error.message || 'Could not load report history.' })
    })
    return () => { current = false }
  }, [owner, historyOpen, client.id, onLoadHistory, historyRevision])

  const saveHistory = async action => {
    try {
      await onRecordAction(action)
      setUnsavedAction(null)
      setActionError('')
      setHistoryRevision(current => current + 1)
    } catch {
      setUnsavedAction(action)
      const activity = action.kind === 'pdf_share_opened' ? 'PDF share opened' : `${PROGRESS_REPORT_ACTIONS[action.kind]} started`
      setActionError(`${activity}, but its history could not be saved.`)
    }
  }
  const recordAction = async (kind, launch) => {
    if (acting.current || unsavedAction) return
    acting.current = true
    setBusy(true)
    setActionError('')
    try {
      const action = { id: `report-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`, kind }
      // Invoke before awaiting so native file sharing retains user activation.
      await launch()
      await saveHistory(action)
      return true
    } catch (error) {
      if (error.name !== 'AbortError') setActionError(error.message || 'The progress report could not be opened.')
      return false
    } finally { acting.current = false; setBusy(false) }
  }
  const retryHistory = async () => {
    if (acting.current || !unsavedAction) return
    acting.current = true; setBusy(true)
    try { await saveHistory(unsavedAction) }
    finally { acting.current = false; setBusy(false) }
  }
  const exportReport = () => recordAction('pdf_export', async () => {
    downloadProgressReport(await progressReportFile(client, { timeZone }))
  })
  const shareReport = () => {
    if (acting.current || unsavedAction) return
    setActionError('')
    setShareClient(structuredClone(client))
  }

  const selectedSummary = selected ? progressSummary(selected) : null
  const actionFeedback = actionError && <div className="report-action-error" role="alert"><p>{actionError}</p>
    {unsavedAction && <button type="button" className="secondary-button" disabled={busy} onClick={retryHistory}>Retry History Save</button>}
  </div>

  return (
    <div className="stack-gap strength-progress" aria-label="Strength progress">
      {owner && <Panel className="report-history-panel">
        <button type="button" className="text-action" aria-expanded={historyOpen}
          aria-controls="progress-report-history" onClick={() => setHistoryOpen(open => !open)}>
          {historyOpen ? 'Hide Export/WhatsApp History' : 'View Export/WhatsApp History'}
        </button>
        {historyOpen && <div id="progress-report-history" className="report-history" aria-label="Export/WhatsApp history">
          {historyState.loading ? <p role="status">Loading history…</p> : historyState.error ? <div role="alert">
            <p>{historyState.error}</p><button type="button" className="secondary-button" onClick={() => setHistoryRevision(current => current + 1)}>Retry History</button>
          </div> : <>
            <div className="report-history-head" aria-hidden="true"><span>Action</span><span>Date &amp; time</span><span>Staff</span></div>
            {historyPages.items.map(entry => <article className="report-history-row" key={entry.id}>
              <strong>{PROGRESS_REPORT_ACTIONS[entry.kind]}</strong>
              <time dateTime={entry.at}>{formatTimestamp(entry.at, timeZone)}</time>
              <span>{entry.by.name}</span>
            </article>)}
            {!historyState.items.length && <p className="empty">No export or WhatsApp history yet.</p>}
            <PaginationControls {...historyPages} onPage={historyPages.setPage} />
          </>}
        </div>}
      </Panel>}
      {!shareClient && actionFeedback}
      {shareClient && <ProgressReportShareDialog client={shareClient} timeZone={timeZone} busy={busy} blocked={Boolean(unsavedAction)}
        onClose={() => setShareClient(null)}
        onShare={file => recordAction('pdf_share_opened', () => navigator.share({ files: [file] }))}
        onDownload={file => recordAction('pdf_export', () => downloadProgressReport(file))}>
        {actionFeedback}
      </ProgressReportShareDialog>}
      {!selected ? <Panel><div className="empty">No completed exercise loads yet.</div></Panel> : <>
      <Panel>
        <div className="strength-progress-head">
          <div className="strength-progress-title">
            <h2>Strength Progress</h2>
            <p>Completed exercise loads over time</p>
          </div>
          <label className="strength-progress-exercise">
            Exercise
            <select aria-label="Strength progress exercise" value={selected.id} onChange={event => setSelectedId(event.target.value)}>
              {exercises.map(exercise => <option key={exercise.id} value={exercise.id}>{exercise.name}</option>)}
            </select>
          </label>
          <div className="strength-progress-actions">
            <button
              type="button"
              className="secondary-button strength-progress-export"
              aria-label="Export Progress Report"
              disabled={busy || Boolean(unsavedAction)}
              onClick={exportReport}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 4v10m0 0 4-4m-4 4-4-4M5 17.5V20h14v-2.5" />
              </svg>
              <span>Export Progress Report</span>
            </button>
            <button
              type="button"
              className="secondary-button strength-progress-share"
              aria-label="Share Progress Report via WhatsApp"
              disabled={busy || Boolean(unsavedAction)}
              onClick={shareReport}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M20 11.7a8 8 0 0 1-11.9 7L4 20l1.3-4A8 8 0 1 1 20 11.7Z" />
                <path d="M8.6 8.1c.2-.4.4-.4.7-.4h.3c.2 0 .4.1.5.4l.8 1.8c.1.3.1.5-.1.7l-.6.7c-.2.2-.1.4 0 .6.7 1.3 1.7 2.3 3.1 2.9.3.1.5.1.7-.1l.8-1c.2-.2.4-.3.7-.2l1.8.8c.3.1.4.3.4.5 0 .4-.2 1.2-.6 1.6-.5.5-1.3.8-2.2.7-1.2-.2-2.8-.7-4.7-2.4-1.6-1.4-2.6-3.1-2.9-4.3-.3-1.1 0-1.8.3-2.3Z" />
              </svg>
              <span>WhatsApp</span>
            </button>
          </div>
        </div>

        <div className="strength-progress-cards">
          {exercises.map(exercise => {
            const exerciseSummary = progressSummary(exercise)
            return (
              <button
                type="button"
                key={exercise.id}
                className={exercise.id === selected.id ? 'selected' : ''}
                onClick={() => setSelectedId(exercise.id)}
              >
                <span>{exercise.shortName ?? exercise.name}</span>
                <strong>{progressNumber(exerciseSummary.latest)} <small>kg</small></strong>
                <em>{progressChange(exerciseSummary.change)} kg</em>
              </button>
            )
          })}
        </div>
      </Panel>

      <Panel className="strength-chart-panel">
        <div className="strength-chart-summary">
          <div>
            <span>{selected.shortName ?? selected.name}</span>
            <strong>{progressNumber(selectedSummary.latest)} <small>kg</small></strong>
          </div>
          <dl>
            <div><dt>Change</dt><dd>{progressChange(selectedSummary.change)} kg</dd></div>
            <div><dt>Completed</dt><dd>{selected.points.length}</dd></div>
          </dl>
        </div>

        <div className="strength-chart-scroll">
          <StrengthProgressChart exercise={selected} />
        </div>
      </Panel>

      </>}
    </div>
  )
}

import usePageState from '../../hooks/usePageState.js'
import { useEffect, useId, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import { PROGRESS_REPORT_ACTIONS } from '../../app/progress.js'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import { formatTimestamp } from '../../utils/date.js'
import { reportShareError } from '../../services/reportService.js'
import useReportService from '../../hooks/useReportService.js'
import usePreparedReport from '../../hooks/usePreparedReport.js'

import StrengthProgressChart from './StrengthProgressChart.jsx'
import { progressNumber, progressSummary, progressChange } from './progressChart.js'

export default function StrengthProgress({ client, user, timeZone, onRecordAction, onLoadHistory }) {
  const exercises = client.strengthProgress ?? []
  const exerciseScope = `${client.id}.${client.reportPackageId ?? 'legacy'}`
  const exercisePages = usePagination(exercises, exerciseScope, `client.${exerciseScope}.exercisePage`)
  const [selectedId, setSelectedId] = usePageState(`StrengthProgress.${client.reportPackageId ?? 'unassigned'}.selectedId`, '')

  const owner = user?.role === 'owner'
  const [historyOpen, setHistoryOpen] = usePageState(`client.${client.id}.reportHistoryOpen`, false)
  const [historyState, setHistoryState] = useState({ items: [], loading: true, error: '' })
  const [historyRevision, setHistoryRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [unsavedAction, setUnsavedAction] = useState(null)
  const reportService = useReportService()
  const report = usePreparedReport(reportService.progressFile, { client, timeZone }, exercises.length > 0)
  const [shareFallback, setShareFallback] = useState(false)
  const acting = useRef(false)

  useEffect(() => {
    if (!owner || !historyOpen) return
    let current = true
    setHistoryState(previous => ({ ...previous, loading: true, error: '' }))
    Promise.resolve().then(() => onLoadHistory(client.reportPackageId)).then(items => {
      if (current) setHistoryState({ items, loading: false, error: '' })
    }).catch(error => {
      if (current) setHistoryState(previous => ({ ...previous, loading: false, error: error.message || 'Could not load report history.' }))
    })
    return () => { current = false }
  }, [owner, historyOpen, client.id, client.reportPackageId, onLoadHistory, historyRevision])

  useEffect(() => {
    if (!owner || !historyOpen) return
    const refresh = () => setHistoryRevision(current => current + 1)
    window.addEventListener('focus', refresh)
    window.addEventListener('storage', refresh)
    return () => { window.removeEventListener('focus', refresh); window.removeEventListener('storage', refresh) }
  }, [owner, historyOpen])

  const saveHistory = async action => {
    try {
      await onRecordAction(action)
      setUnsavedAction(null)
      setActionError('')
      setHistoryRevision(current => current + 1)
    } catch {
      setUnsavedAction(action)
      const activity = action.kind.endsWith('_opened') ? PROGRESS_REPORT_ACTIONS[action.kind] : `${PROGRESS_REPORT_ACTIONS[action.kind]} started`
      setActionError(`${activity}, but its history could not be saved.`)
    }
  }
  const recordAction = async (kind, launch) => {
    if (acting.current || unsavedAction) return
    acting.current = true
    setBusy(true)
    setActionError('')
    try {
      const action = { id: `report-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`, kind, ...(Object.hasOwn(client, 'reportPackageId') ? { packageId: client.reportPackageId } : {}) }
      // Invoke before awaiting so native file sharing retains user activation.
      await launch()
      await saveHistory(action)
      return true
    } catch (error) {
      if (error.name !== 'AbortError') setActionError(kind === 'pdf_share_opened' ? reportShareError(error) : error.message || 'The progress report could not be opened.')
      return false
    } finally { acting.current = false; setBusy(false) }
  }
  const retryHistory = async () => {
    if (acting.current || !unsavedAction) return
    acting.current = true; setBusy(true)
    try { await saveHistory(unsavedAction) }
    finally { acting.current = false; setBusy(false) }
  }
  const exportReport = () => recordAction('pdf_export', () => reportService.download(report.file))
  const shareReport = () => {
    if (acting.current || unsavedAction || !report.file) return
    setShareFallback(!reportService.canShare(report.file))
    return recordAction('pdf_share_opened', () => reportService.share(report.file))
  }
  const openReport = () => {
    try { reportService.open(report.file); setActionError('') }
    catch (error) { setActionError(error.message) }
  }

  const actionFeedback = actionError && <div className="report-action-error" role="alert"><p>{actionError}</p>
    {unsavedAction && <button type="button" className="secondary-button" disabled={busy} onClick={retryHistory}>Retry History Save</button>}
  </div>

  return (
    <div className="stack-gap strength-progress" aria-label="Strength progress">
      {owner && <Panel className="report-history-panel">
        <button type="button" className="secondary-button small" aria-expanded={historyOpen}
          aria-controls="progress-report-history" onClick={() => setHistoryOpen(open => !open)}>
          {historyOpen ? 'Hide Export/WhatsApp History' : 'View Export/WhatsApp History'}
        </button>
        {historyOpen && <div id="progress-report-history" className="report-history" aria-label="Export/WhatsApp history">
          {historyState.loading && !historyState.items.length && <p role="status">Loading history…</p>}
          {historyState.error && <div role="alert">
            <p>{historyState.error}</p><button type="button" className="secondary-button" onClick={() => setHistoryRevision(current => current + 1)}>Retry History</button>
          </div>}
          {(!historyState.loading && !historyState.error || historyState.items.length > 0) &&
            <ReportHistoryRows clientId={client.id} packageId={client.reportPackageId} items={historyState.items} timeZone={timeZone} />}
        </div>}
      </Panel>}
      {actionFeedback}
      {report.preparing && <p role="status">Preparing PDF…</p>}
      {report.error && <div role="alert"><p>{report.error}</p><button type="button" className="secondary-button" onClick={report.retry}>Retry PDF</button></div>}
      {shareFallback && report.file && <div className="report-file-actions"><button type="button" className="secondary-button" disabled={busy || Boolean(unsavedAction)} onClick={openReport}>Open PDF</button></div>}
      {!exercises.length ? <Panel><div className="empty">No completed exercise loads yet.</div></Panel> : <Panel>
        <div className="strength-progress-head">
          <div className="strength-progress-title">
            <h2>Strength Progress</h2>
            <p>Completed exercise loads over time</p>
          </div>
          <div className="strength-progress-actions">
            <button
              type="button"
              className="secondary-button strength-progress-export"
              aria-label="Download Progress Report PDF"
              disabled={busy || Boolean(unsavedAction) || !report.file}
              onClick={exportReport}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 4v10m0 0 4-4m-4 4-4-4M5 17.5V20h14v-2.5" />
              </svg>
              <span>Download PDF</span>
            </button>
            <button
              type="button"
              className="secondary-button strength-progress-share"
              aria-label="Share Progress Report PDF"
              disabled={busy || Boolean(unsavedAction) || !report.file}
              onClick={shareReport}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 16V3m0 0-4 4m4-4 4 4M7 10H4v11h16V10h-3" />
              </svg>
              <span>Share PDF</span>
            </button>
          </div>
        </div>

        <div className="strength-progress-list" aria-label="Exercise progress">
          <div className="strength-progress-columns" aria-hidden="true">
            <span>Exercise</span><span>Latest</span><span>Change</span><span>Completed</span><span />
          </div>
          {exercisePages.items.map(exercise => <ExerciseProgressRow key={exercise.id} exercise={exercise} expanded={exercise.id === selectedId}
            onToggle={() => setSelectedId(current => current === exercise.id ? '' : exercise.id)} />)}
        </div>
        <PaginationControls {...exercisePages} onPage={exercisePages.setPage} />
      </Panel>}
    </div>
  )
}

function ReportHistoryRows({ clientId, packageId, items, timeZone }) {
  const scope = `${clientId}.${packageId ?? 'legacy'}`
  // Mount pagination only with loaded records, so an empty loading state cannot
  // clamp a saved page or feed navigation writes back into history loading.
  const pages = usePagination(items, scope, `client.${scope}.reportHistoryPage`)
  return <>
    <div className="report-history-head" aria-hidden="true"><span>Action</span><span>Date &amp; time</span><span>Staff</span></div>
    {pages.items.map(entry => <article className="report-history-row" key={entry.id}>
      <strong>{PROGRESS_REPORT_ACTIONS[entry.kind]}</strong>
      <time dateTime={entry.at}>{formatTimestamp(entry.at, timeZone)}</time>
      <span>{entry.by.name}</span>
    </article>)}
    {!items.length && <p className="empty">No export or WhatsApp history yet.</p>}
    <PaginationControls {...pages} onPage={pages.setPage} />
  </>
}

function ExerciseProgressRow({ exercise, expanded, onToggle }) {
  const chartId = useId()
  const summary = progressSummary(exercise)
  return <article className="strength-progress-item">
    <button type="button" className="strength-progress-row" aria-expanded={expanded} aria-controls={chartId}
      aria-label={`${expanded ? 'Hide' : 'Show'} ${exercise.name} progress chart`} onClick={onToggle}>
      <strong className="strength-progress-name">{exercise.name}</strong>
      <span>{progressNumber(summary.latest)} <small>kg</small></span>
      <em className={summary.change < 0 ? 'negative' : undefined}>{progressChange(summary.change)} <small>kg</small></em>
      <span>{exercise.points.length}</span>
      <span className="strength-progress-chevron" aria-hidden="true">›</span>
    </button>
    <div className="strength-chart-panel" id={chartId} hidden={!expanded}>
      {expanded && <>
        <div className="strength-chart-summary">
          <div><span>{exercise.shortName ?? exercise.name}</span><strong>{progressNumber(summary.latest)} <small>kg</small></strong></div>
          <dl>
            <div><dt>Change</dt><dd>{progressChange(summary.change)} kg</dd></div>
            <div><dt>Completed</dt><dd>{exercise.points.length}</dd></div>
          </dl>
        </div>
        <StrengthProgressChart exercise={exercise} />
      </>}
    </div>
  </article>
}

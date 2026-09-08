import usePageState from '../../hooks/usePageState.js'
import { useEffect, useMemo, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import { PROGRESS_REPORT_ACTIONS } from '../../app/progress.js'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import { formatDate, formatTimestamp } from '../../utils/date.js'
import { progressReportCsv, progressReportFilename, progressReportWhatsAppText } from './progressReport.js'

const CHART = { left: 58, right: 870, top: 30, bottom: 232 }

function number(value) {
  return Number.isInteger(value) ? String(value) : String(value).replace(/\.0$/, '')
}

function summary(exercise) {
  const first = exercise.points[0]?.load ?? 0
  const latest = exercise.points.at(-1)?.load ?? 0
  return { first, latest, change: latest - first }
}

function chartPoints(exercise) {
  const values = exercise.points.map(point => point.load)
  const maximum = Math.max(...values, 1)
  const minimum = Math.min(...values, 0)
  const padding = Math.max(5, (maximum - minimum) * 0.25)
  const low = Math.max(0, minimum - padding)
  const high = maximum + padding
  const width = CHART.right - CHART.left
  const height = CHART.bottom - CHART.top

  return exercise.points.map((point, index) => ({
    ...point,
    x: CHART.left + (exercise.points.length === 1 ? width / 2 : (index / (exercise.points.length - 1)) * width),
    y: CHART.bottom - ((point.load - low) / (high - low || 1)) * height,
  }))
}

export default function StrengthProgress({ client, user, timeZone, onRecordAction, onLoadHistory }) {
  const exercises = client.strengthProgress ?? []
  const [selectedId, setSelectedId] = usePageState('StrengthProgress.selectedId', exercises[0]?.id ?? '')
  const selected = exercises.find(exercise => exercise.id === selectedId) ?? exercises[0]
  const points = useMemo(() => selected ? chartPoints(selected) : [], [selected])

  const owner = user?.role === 'owner'
  const [historyOpen, setHistoryOpen] = usePageState(`client.${client.id}.reportHistoryOpen`, false)
  const [historyState, setHistoryState] = useState({ items: [], loading: false, error: '' })
  const [historyRevision, setHistoryRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [unsavedAction, setUnsavedAction] = useState(null)
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
      setActionError(`${PROGRESS_REPORT_ACTIONS[action.kind]} started, but its history could not be saved.`)
    }
  }
  const recordAction = async (kind, launch) => {
    if (acting.current || unsavedAction) return
    acting.current = true
    setBusy(true)
    setActionError('')
    try {
      const action = { id: `report-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`, kind }
      // Launch synchronously while browser user activation is still available.
      launch()
      await saveHistory(action)
    } catch (error) {
      setActionError(error.message || 'The progress report could not be opened.')
    } finally { acting.current = false; setBusy(false) }
  }
  const retryHistory = async () => {
    if (acting.current || !unsavedAction) return
    acting.current = true; setBusy(true)
    try { await saveHistory(unsavedAction) }
    finally { acting.current = false; setBusy(false) }
  }
  const exportReport = () => recordAction('csv_export', () => {
    const blob = new Blob([`\uFEFF${progressReportCsv(client)}`], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    try {
      link.href = url
      link.download = progressReportFilename(client)
      document.body.append(link)
      link.click()
    } finally {
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 0)
    }
  })
  const shareReport = event => {
    event.preventDefault()
    void recordAction('whatsapp_opened', () => {
      let popup
      try {
        popup = window.open('about:blank', '_blank')
        if (!popup) throw new Error('blocked')
        popup.opener = null
        popup.location.replace(whatsappReportUrl)
      } catch {
        popup?.close()
        throw new Error('WhatsApp could not be opened. Allow pop-ups and try again.')
      }
    })
  }

  const selectedSummary = selected ? summary(selected) : null
  const phone = (typeof client.phone === 'string'
    ? client.phone
    : `${client.phone?.countryCode ?? ''}${client.phone?.number ?? ''}`
  ).replace(/\D/g, '')
  const whatsappReportUrl = `https://wa.me/${phone}?text=${encodeURIComponent(progressReportWhatsAppText(client))}`
  const line = points.map(point => `${point.x},${point.y}`).join(' ')
  const area = `${CHART.left},${CHART.bottom} ${line} ${CHART.right},${CHART.bottom}`

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
      {actionError && <div className="report-action-error" role="alert"><p>{actionError}</p>
        {unsavedAction && <button type="button" className="secondary-button" disabled={busy} onClick={retryHistory}>Retry History Save</button>}
      </div>}
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
            <a
              className="secondary-button strength-progress-share"
              aria-label="Share Progress Report via WhatsApp"
              href={whatsappReportUrl}
              aria-disabled={busy || Boolean(unsavedAction)}
              onClick={shareReport}
              target="_blank"
              rel="noreferrer"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M20 11.7a8 8 0 0 1-11.9 7L4 20l1.3-4A8 8 0 1 1 20 11.7Z" />
                <path d="M8.6 8.1c.2-.4.4-.4.7-.4h.3c.2 0 .4.1.5.4l.8 1.8c.1.3.1.5-.1.7l-.6.7c-.2.2-.1.4 0 .6.7 1.3 1.7 2.3 3.1 2.9.3.1.5.1.7-.1l.8-1c.2-.2.4-.3.7-.2l1.8.8c.3.1.4.3.4.5 0 .4-.2 1.2-.6 1.6-.5.5-1.3.8-2.2.7-1.2-.2-2.8-.7-4.7-2.4-1.6-1.4-2.6-3.1-2.9-4.3-.3-1.1 0-1.8.3-2.3Z" />
              </svg>
              <span>WhatsApp</span>
            </a>
          </div>
        </div>

        <div className="strength-progress-cards">
          {exercises.map(exercise => {
            const exerciseSummary = summary(exercise)
            return (
              <button
                type="button"
                key={exercise.id}
                className={exercise.id === selected.id ? 'selected' : ''}
                onClick={() => setSelectedId(exercise.id)}
              >
                <span>{exercise.shortName ?? exercise.name}</span>
                <strong>{number(exerciseSummary.latest)} <small>kg</small></strong>
                <em>+{number(exerciseSummary.change)} kg</em>
              </button>
            )
          })}
        </div>
      </Panel>

      <Panel className="strength-chart-panel">
        <div className="strength-chart-summary">
          <div>
            <span>{selected.shortName ?? selected.name}</span>
            <strong>{number(selectedSummary.latest)} <small>kg</small></strong>
          </div>
          <dl>
            <div><dt>Change</dt><dd>+{number(selectedSummary.change)} kg</dd></div>
            <div><dt>Completed</dt><dd>{selected.points.length}</dd></div>
          </dl>
        </div>

        <div className="strength-chart-scroll">
          <svg className="strength-chart" viewBox="0 0 900 280" role="img" aria-label={`${selected.name} load progress chart`}>
            <defs>
              <linearGradient id="strength-line" x1="0" x2="1">
                <stop offset="0" stopColor="#ff3e9c" />
                <stop offset="1" stopColor="#6676ff" />
              </linearGradient>
              <linearGradient id="strength-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#6676ff" stopOpacity=".25" />
                <stop offset="1" stopColor="#6676ff" stopOpacity="0" />
              </linearGradient>
            </defs>

            {[0, 1, 2, 3, 4].map(index => {
              const y = CHART.top + ((CHART.bottom - CHART.top) / 4) * index
              return <line key={index} x1={CHART.left} x2={CHART.right} y1={y} y2={y} className="strength-grid-line" />
            })}

            <text x="18" y="142" className="strength-axis-title" transform="rotate(-90 18 142)">Load (kg)</text>
            <polygon points={area} fill="url(#strength-area)" />
            <polyline points={line} fill="none" stroke="url(#strength-line)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />

            {points.map((point, index) => (
              <g key={point.id}>
                <circle cx={point.x} cy={point.y} r={index === points.length - 1 ? 7 : 5} className={index === points.length - 1 ? 'latest' : ''} />
                <text x={point.x} y={point.y - 13} textAnchor="middle" className="strength-load-label">{number(point.load)}</text>
                <text x={point.x} y="258" textAnchor="middle" className="strength-date-label">{formatDate(point.date).replace(/ \d{4}$/, '')}</text>
              </g>
            ))}
          </svg>
        </div>
      </Panel>

      </>}
    </div>
  )
}

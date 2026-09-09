import { useEffect, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import { canShareProgressReport, progressReportFile } from './progressReport.js'

export default function ProgressReportShareDialog({ client, timeZone, busy, blocked, onShare, onDownload, onClose, children }) {
  const [report, setReport] = useState({ file: null, error: '' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    setReport({ file: null, error: '' })
    progressReportFile(client, { timeZone }).then(file => {
      if (active) setReport({ file, error: '' })
    }).catch(error => {
      if (active) setReport({ file: null, error: error.message || 'Could not prepare the PDF.' })
    })
    return () => { active = false }
  }, [client, timeZone, attempt])

  const supported = canShareProgressReport(report.file)
  const phone = (typeof client.phone === 'string' ? client.phone : `${client.phone?.countryCode ?? ''}${client.phone?.number ?? ''}`).replace(/\D/g, '')
  return <ConfirmDialog open title="Share Progress Report" confirmLabel="Share PDF" cancelLabel="Close"
    hideConfirm={!supported} confirmDisabled={busy || blocked} onCancel={() => { if (!busy) onClose() }}
    onConfirm={async () => {
      // This second, explicit click retains user activation after a long PDF render.
      if (report.file && !busy && !blocked && await onShare(report.file)) onClose()
    }}>
    {!report.file && !report.error && <p role="status">Preparing PDF…</p>}
    {report.error && <div role="alert"><p>{report.error}</p><button type="button" className="secondary-button" onClick={() => setAttempt(value => value + 1)}>Retry PDF</button></div>}
    {report.file && <>
      <p className="report-file-name">{report.file.name}</p>
      <p className="muted">{supported ? 'Choose WhatsApp in the share menu.' : 'Download the PDF and attach it in WhatsApp.'}</p>
      <div className="report-file-actions">
        <button type="button" className="secondary-button" disabled={busy || blocked} onClick={() => onDownload(report.file)}>Download PDF</button>
        {phone && <a className="secondary-button" href={`https://wa.me/${phone}`} target="_blank" rel="noreferrer">Open WhatsApp</a>}
      </div>
    </>}
    {children}
  </ConfirmDialog>
}

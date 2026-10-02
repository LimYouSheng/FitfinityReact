import { useEffect, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import { exerciseVideoCaption } from './exerciseVideo.js'
import useReportService from '../../hooks/useReportService.js'
import usePreparedReport from '../../hooks/usePreparedReport.js'
import { reportShareError } from '../../services/reportService.js'

export default function SessionSummaryExport({ client, session, displayedSummary, recordInactive, activeEditor, requestKind, dateError, checkTrainingDate, saving, setSaving }) {
  const [exportOpen, setExportOpen] = useState(false)
  const [shareError, setShareError] = useState('')
  const [selectedVideoIds, setSelectedVideoIds] = useState([])
  const [includeClientSummary, setIncludeClientSummary] = useState(true)
  const recordedVideos = (session.exercisePlan ?? []).filter(item => item.videoAttached)
  const selectedVideos = recordedVideos.filter(item => selectedVideoIds.includes(item.id))
  const hasExportSelection = selectedVideos.length > 0 || (includeClientSummary && Boolean(displayedSummary.trim()))
  const reportService = useReportService()
  const report = usePreparedReport(reportService.sessionFile, { client, session, summary: includeClientSummary ? displayedSummary : '', videos: selectedVideos }, exportOpen && hasExportSelection)

  useEffect(() => { if (recordInactive) setExportOpen(false) }, [recordInactive])

  const openExportSummary = () => {
    if (recordInactive || !checkTrainingDate()) return
    setSelectedVideoIds(recordedVideos.map(item => item.id))
    setIncludeClientSummary(true)
    setShareError('')
    setExportOpen(true)
  }

  const exportSummary = async () => {
    if (saving || !checkTrainingDate() || !hasExportSelection || !report.file) return
    setShareError('')
    setSaving(true)
    try {
      // Already prepared: invoke the device share from the explicit click.
      await reportService.share(report.file)
      setExportOpen(false)
    } catch (error) {
      if (error.name !== 'AbortError') setShareError(reportShareError(error))
    } finally { setSaving(false) }
  }


  return (
    <>
            <button
              type="button"
              className="session-action-button session-export-summary-button"
              disabled={Boolean(recordInactive || activeEditor || requestKind || saving || dateError)}
              title={dateError ?? undefined}
              onClick={openExportSummary}
            >
              Export Summary
            </button>
          <ConfirmDialog
            open={exportOpen}
            title="Export Summary"
            confirmLabel={saving ? 'Sharing…' : 'Share PDF'}
            confirmDisabled={saving || Boolean(dateError) || !hasExportSelection || !report.file}
            onCancel={() => { if (!saving) setExportOpen(false) }}
            onConfirm={exportSummary}
          >
            <fieldset className="export-summary-section" disabled={saving}>
            <legend>Selected Videos</legend>
            {recordedVideos.length ? (
              <div className="export-video-list">
                {recordedVideos.map(item => (
                  <label className="export-video-option" key={item.id}>
                    <input
                      type="checkbox"
                      aria-label={`Include video for ${item.name}`}
                      checked={selectedVideoIds.includes(item.id)}
                      onChange={() => { setShareError(''); setSelectedVideoIds(current => current.includes(item.id)
                        ? current.filter(id => id !== item.id)
                        : [...current, item.id]) }}
                    />
                    <span>
                      <strong>{item.name}</strong>
                      <small>{exerciseVideoCaption(item)}</small>
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="empty">No videos</p>
            )}
            </fieldset>
            <fieldset className="export-summary-section" disabled={saving}>
              <legend>Select Client Facing Summary</legend>
              <label className="export-summary-option">
                <input type="checkbox" aria-label="Include Client-Facing Summary" checked={includeClientSummary}
                  onChange={event => { setIncludeClientSummary(event.target.checked); setShareError('') }} />
                <span>Client-Facing Summary</span>
              </label>
              {includeClientSummary && <div className="client-summary-copy">{displayedSummary}</div>}
            </fieldset>
            {report.preparing && <p role="status">Preparing PDF…</p>}
            {report.error && <div role="alert"><p>{report.error}</p><button type="button" className="secondary-button" onClick={report.retry}>Retry PDF</button></div>}
            {shareError && <p role="alert">{shareError}</p>}
            {report.file && <div className="report-file-actions"><button type="button" className="secondary-button" disabled={saving} onClick={() => {
              try { reportService.download(report.file); setShareError('') }
              catch (error) { setShareError(error.message) }
            }}>Download PDF</button></div>}
          </ConfirmDialog>

    </>
  )
}

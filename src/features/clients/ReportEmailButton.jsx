import { useContext, useEffect, useRef, useState } from 'react'
import { PortalData } from '../../hooks/usePortalData.js'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useNotifications } from '../../components/NotificationProvider.jsx'
import LoadingIndicator from '../../components/LoadingIndicator.jsx'

/** Email only after explicit recipient review; preparing/approving never queues a send. */
export default function ReportEmailButton({ clientId, purchaseId, disabled }) {
  const services = useContext(PortalData)?.services
  return services?.sendReportEmail ? <ReportEmailAction key={`${clientId}:${purchaseId}`} services={services} clientId={clientId} purchaseId={purchaseId} disabled={disabled} /> : null
}

function ReportEmailAction({ services, clientId, purchaseId, disabled }) {
  const confirm = useActionConfirmation()
  const { notify } = useNotifications()
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [retry, setRetry] = useState(false)
  const [approvalRetry, setApprovalRetry] = useState(false)
  const [approval, setApproval] = useState(false)
  const lock = useRef(false), lifetime = useRef(0)
  useEffect(() => { lifetime.current += 1; return () => { lifetime.current += 1 } }, [clientId, purchaseId, services])
  const send = async () => {
    if (lock.current) return
    lock.current = true; setBusy(true)
    const token = lifetime.current
    const current = () => lifetime.current === token
    const selection = { kind: 'progress', targetId: clientId, purchaseId, includeSummary: true, videoIds: [] }
    let stage = uncertain ? 'email' : 'approval'
    try {
      if (uncertain) {
        await (retry ? services.retryReportEmail(selection) : services.recoverReportEmail(selection))
      } else {
        await (approvalRetry ? services.retryReportSharing(selection) : services.prepareReportSharing(selection))
        setApprovalRetry(false)
        stage = 'email'
        const reviewed = await services.reviewReportEmail(selection)
        if (!current()) return
        setBusy(false)
        const accepted = await confirm({ title: 'Email progress report?', confirmLabel: 'Send Email',
          message: `Send a plain-text progress report to ${reviewed.recipients.map(p => `${p.name} (${p.email})`).join(', ')}? No private trainer comments or video files are included.` })
        if (!accepted || !current()) return
        setBusy(true)
        try { await services.sendReportEmail({ ...selection, expected: reviewed.expected }) }
        catch (error) {
          if (current() && !(error.status >= 400 && error.status < 500)) setUncertain(true)
          throw error
        }
      }
      if (current()) {
        setUncertain(false); setRetry(false); setApproval(false)
        notify({ message: 'Progress report email queued. Delivery is not yet confirmed.' })
      }
    } catch (error) {
      if (current()) {
        setApproval(error.code === 'APPROVAL_PENDING')
        if (error.code === 'SAVE_UNCERTAIN') {
          if (stage === 'email') setUncertain(true)
          else setApprovalRetry(true)
        }
        if (uncertain && error.code === 'SAVE_UNCERTAIN') setRetry(true)
        notify({ tone: error.code === 'APPROVAL_PENDING' ? 'info' : 'error', message: error.code === 'APPROVAL_PENDING' ? 'Waiting for Owner approval. Check again after the report is approved.' : error.message })
      }
    } finally {
      lock.current = false
      if (current()) setBusy(false)
    }
  }
  const label = uncertain ? (retry ? 'Retry Original Email' : 'Check Original Email') : approvalRetry ? 'Retry Report Preparation' : approval ? 'Check Email Approval' : 'Email Report'
  return <>
    {busy && <LoadingIndicator label="Preparing report email…" />}
    <button type="button" className="secondary-button strength-progress-share" aria-label={label} title={label} disabled={busy || disabled} onClick={send}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18v14H3zM3 5l9 7 9-7" /></svg>
      <span>{label}</span>
    </button>
  </>
}

import ExerciseLibraryMedia from '../exercises/ExerciseLibraryMedia.jsx'
import useReportService from '../../hooks/useReportService.js'
import usePreparedReport from '../../hooks/usePreparedReport.js'
const OPERATIONS = {
  'report.progress': 'Share progress report', 'report.session': 'Share session PDF',
  'undo.clientPackages': 'Restore deleted package sessions',
  'undo.sessionScheduling': 'Undo schedule change', 'undo.sessionContent': 'Undo session content change',
  'undo.trainerAssignment': 'Undo Trainer assignment', 'undo.clientLifecycle': 'Undo client lifecycle change',
  'undo.trainerLifecycle': 'Undo Trainer lifecycle change',
  'library.publish': 'Save Exercise Library entry',
  'trainer.create': 'Create Trainer and send invitation',
  'trainer.email': 'Request verified Trainer email change',
  'client.create': 'Create client', 'client.details': 'Client details', 'client.notes': 'Client notes',
  'client.deactivate': 'Deactivate client', 'client.reactivate': 'Reactivate client',
  'client.assignment': 'Change client Trainer', 'client.weekly': 'Change weekly schedule',
  'client.purchase': 'Add purchased package', 'purchase.reactivate': 'Reactivate purchased package',
  'purchase.action': 'Purchased package action', 'trainer.details': 'Trainer details',
  'trainer.approvals': 'Trainer approval requirements', 'trainer.deactivate': 'Deactivate Trainer',
  'trainer.reactivate': 'Reactivate Trainer', 'assessment.create': 'Create assessment',
  'assessment.save': 'Assessment revision', 'request.resolve': 'Decide scheduling request',
  'session.booking': 'Change session booking', 'session.postpone': 'Postpone session',
  'session.plan': 'Replace exercise plan', 'session.copy_plan': 'Copy previous exercise plan',
  'session.outcome': 'Session outcomes', 'session.summary': 'Session summary',
  'session.acknowledge': 'Acknowledge session',
}
const hidden = new Set(['expected', 'request_sha256', 'actor_id', 'actor_name', 'created_at', 'updated_at'])
const label = key => key.replaceAll('_', ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/\bId\b/g, 'ID').replace(/^./, value => value.toUpperCase())
export function reviewableOperation(proposal) {
  return Boolean(OPERATIONS[proposal?.operation] && proposal.body?.body && typeof proposal.body.body === 'object' && proposal.body.review && typeof proposal.body.review === 'object')
}
function Fields({ value }) {
  if (value === null || value === undefined) return <span>None</span>
  if (typeof value === 'boolean') return <span>{value ? 'Yes' : 'No'}</span>
  if (typeof value !== 'object') return <span style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{String(value)}</span>
  if (Array.isArray(value)) return value.length ? <ol>{value.map((item, index) => <li key={index}><Fields value={item} /></li>)}</ol> : <span>None</span>
  return <dl className="info-list">{Object.entries(value).filter(([key]) => !hidden.has(key)).map(([key, item]) => <div key={key}><dt>{label(key)}</dt><dd><Fields value={item} /></dd></div>)}</dl>
}
function ReportPreview({ report }) {
  const service = useReportService()
  const prepared = usePreparedReport(report.kind === 'progress' ? service.progressFile : service.sessionFile, report.inputs)
  return <div>
    {prepared.preparing && <p role="status">Preparing reviewed PDF…</p>}
    {prepared.error && <p role="alert">{prepared.error}</p>}
    <button type="button" className="secondary-button" disabled={!prepared.file} onClick={() => service.download(prepared.file)}>Download Reviewed PDF</button>
    <p>Approval permits the requesting Admin to share this report. It does not send the report.</p>
  </div>
}
export default function AdminProposalReview({ proposal, services }) {
  if (!reviewableOperation(proposal)) return null
  return <article><h3>{OPERATIONS[proposal.operation]}</h3>
    {proposal.body.review.subject && <p>{proposal.body.review.subject}</p>}
    <h4>Requested change</h4><Fields value={proposal.body.review.proposed ?? proposal.body.body} />
    {proposal.operation.startsWith('report.') && <ReportPreview report={proposal.body.review.proposed} />}
    {proposal.operation === 'library.publish' && proposal.status === 'pending' && proposal.body.review.proposed?.attachment && <ExerciseLibraryMedia media={proposal.body.review.proposed.attachment} onLoad={() => services.readAdminAttachment({ id: proposal.id })} />}
    {proposal.body.review.before && <details><summary>State captured when submitted</summary><Fields value={proposal.body.review.before} /></details>}
    <p>Approval rechecks the current records. A changed record may require a new request.</p>
  </article>
}

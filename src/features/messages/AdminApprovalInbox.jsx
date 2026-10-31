import AdminProposalReview, { reviewableOperation } from './AdminProposalReview.jsx'
import { useEffect, useEffectEvent, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { contentErrors } from '../../app/content.js'
import { ADMIN_APPROVAL_FIELDS } from '../../app/adminApprovals.js'

export default function AdminApprovalInbox({ services, user }) {
  const [items, setItems] = useState(null)
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [attempt, setAttempt] = useState(null)
  const confirm = useActionConfirmation()
  const load = useEffectEvent(() => services.readAdminRequests())
  useEffect(() => {
    let current = true
    load().then(value => {
      if (!current) return
      setItems(value.items); setAttempt(value.pending); setError('')
      setSelected(value.pending ? value.items.find(item => item.id === value.pending.id) ?? null : null)
    }).catch(failure => { if (current) setError(failure.message) })
    return () => { current = false }
  }, [revision])
  const pagination = usePagination(items ?? [], user.id, 'messages.adminApprovalsPage')
  const accept = result => {
    setItems(rows => (rows ?? []).map(row => row.id === result.id ? result : row))
    setSelected(result); setAttempt(null); setError('')
  }
  const decide = async decision => {
    if (busy || !selected) return
    const input = attempt ?? { id: selected.id, expectedVersion: selected.version, decision }
    const label = { approved: 'Approve', rejected: 'Reject', cancelled: 'Cancel Request' }[input.decision]
    if (!attempt && !await confirm({ title: `${label}?`, message: input.decision === 'approved' ? 'Apply the exact reviewed change if the record and permissions are still current.' : 'The proposed change will not be applied.', confirmLabel: label })) return
    setBusy(true); setError(''); setAttempt(input)
    try { accept(await services.decideAdminRequest(input)) }
    catch (failure) {
      setError(failure.message)
      if (failure.status >= 400 && failure.status < 500) setAttempt(null)
    } finally { setBusy(false) }
  }
  const check = async () => {
    if (busy) return
    setBusy(true); setError('')
    try {
      const result = await services.recoverAdminDecision()
      if (result) accept(result.result)
      else setError('The original decision is not confirmed yet. You can check again or retry the same decision.')
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  const draft = selected?.body?.body?.draft
  const contentReview = selected?.operation === 'content.save' && draft &&
    ['title', 'key', 'body', 'status'].every(key => typeof draft[key] === 'string') && !Object.keys(contentErrors(draft)).length
  const packageReview = selected?.operation === 'package.save' && draft && typeof draft.name === 'string' &&
    draft.name.trim().length > 0 && draft.name.length <= 80 && Number.isInteger(draft.total) && draft.total >= 1 && draft.total <= 365 && ['active', 'inactive'].includes(draft.status)
  const domainReview = reviewableOperation(selected)
  const reviewable = contentReview || packageReview || domainReview
  return <Panel>
    <div className="section-heading"><h2>Admin Requests</h2><button type="button" className="text-action" disabled={busy || Boolean(attempt)} onClick={() => { setItems(null); setRevision(value => value + 1) }}>Refresh Requests</button></div>
    {error && <p role="alert">{error}</p>}
    {!items && !error && <p role="status">Loading Admin requests…</p>}
    {items?.length === 0 && <p className="empty">No Admin requests.</p>}
    {!selected && <>
      <div className="info-list">{pagination.items.map(item => <div className="info-row" key={item.id}>
        <span>{item.actorName} · {ADMIN_APPROVAL_FIELDS.find(([area]) => area === item.area)?.[1]} · {item.status}</span>
        <button type="button" className="text-action" onClick={() => setSelected(item)}>Review</button>
      </div>)}</div><PaginationControls {...pagination} onPage={pagination.setPage} />
    </>}
    {selected && <div className="stack-gap">
      <p>{selected.actorName} · {selected.status}</p>
      {(contentReview || packageReview) && <p>{selected.body.body.id ? `Update record ${selected.body.body.id} · reviewed version ${selected.body.body.expectedVersion}` : 'Create a new record'}</p>}
      {contentReview ? <article className="content-preview"><h3>{draft.title}</h3><p>{draft.key} · {draft.status}</p><p>{draft.body}</p></article>
        : packageReview ? <article><h3>{draft.name}</h3><p>{draft.total} sessions · {draft.status}</p><p>Existing purchased terms remain unchanged.</p></article>
        : domainReview ? <AdminProposalReview proposal={selected} services={services} />
        : <p>This request cannot be fully reviewed in this version. Approval is unavailable.</p>}
      {selected.status === 'pending' && (attempt ? <div className="section-actions">
        <button type="button" disabled={busy} onClick={check}>Check Original Decision</button>
        <button type="button" disabled={busy} onClick={() => decide(attempt.decision)}>Retry Original Decision</button>
      </div> : <div className="section-actions">
        {user.role === 'owner' && <><button type="button" className="primary-button" disabled={busy || !reviewable} onClick={() => decide('approved')}>Approve</button><button type="button" className="secondary-button" disabled={busy} onClick={() => decide('rejected')}>Reject</button></>}
        {user.role === 'admin' && selected.actorId === user.id && <button type="button" disabled={busy} onClick={() => decide('cancelled')}>Cancel Request</button>}
      </div>)}
      <button type="button" className="text-action" disabled={busy || Boolean(attempt)} onClick={() => setSelected(null)}>Back to Requests</button>
    </div>}
  </Panel>
}

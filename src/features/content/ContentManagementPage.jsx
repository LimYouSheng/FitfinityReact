import { useEffect, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { contentErrors } from '../../app/content.js'

const draftFor = entry => ({ title: entry?.title ?? '', key: entry?.key ?? '', body: entry?.body ?? '', status: entry?.status ?? 'draft' })
const statuses = { draft: 'Draft', ready: 'Ready', archived: 'Archived' }

function ContentEditor({ entry, onSave, onNavigate }) {
  const [draft, setDraft] = useState(() => draftFor(entry))
  const [errors, setErrors] = useState({})
  const [error, setError] = useState('')
  const [preview, setPreview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(null)
  const pending = useRef(false)
  const { setActiveEdit, activeEdit } = useEditGuard()
  const confirm = useActionConfirmation()
  const dirty = !saved && JSON.stringify(draft) !== JSON.stringify(draftFor(entry))
  useEffect(() => { setActiveEdit(dirty ? 'Website content' : null); return () => setActiveEdit(null) }, [dirty, setActiveEdit])
  useEffect(() => { if (saved && !activeEdit) onNavigate(`content/${saved.id}`, { replace: true }) }, [saved, activeEdit, onNavigate])
  const patch = (field, value) => { setDraft(current => ({ ...current, [field]: value })); setErrors({}); setError('') }
  const submit = async event => {
    event.preventDefault()
    if (pending.current) return
    const validation = contentErrors(draft); setErrors(validation)
    if (Object.keys(validation).length) return
    pending.current = true; setBusy(true)
    try {
      if (!await confirm({ title: 'Save content?', message: `${draft.title.trim()} · ${statuses[draft.status]}`, confirmLabel: 'Save Content' })) return
      const result = await onSave({ id: entry?.id, expectedVersion: entry?.version, draft })
      setSaved(result); setActiveEdit(null)
    } catch (failure) { setError(failure.message || 'Could not save content. Try again.') }
    finally { pending.current = false; setBusy(false) }
  }
  if (saved) return <Panel><h2>{saved.title}</h2><p>{saved.key} · {statuses[saved.status]}</p><article className="content-preview"><p>{saved.body}</p></article><button type="button" className="secondary-button" onClick={() => { setSaved(null); setDraft(draftFor(saved)) }}>Edit Content</button><button type="button" className="secondary-button" onClick={() => onNavigate('content')}>Back to Content</button></Panel>
  return <Panel className={dirty ? 'editing-section' : ''}>
    <form className="content-form" onSubmit={submit} noValidate>
      <fieldset disabled={busy}>
        <label>Title<input aria-label="Content title" value={draft.title} maxLength={180} onChange={event => patch('title', event.target.value)} />{errors.title && <small role="alert">{errors.title}</small>}</label>
        <label>Content key<input aria-label="Content key" value={draft.key} maxLength={120} onChange={event => patch('key', event.target.value)} />{errors.key && <small role="alert">{errors.key}</small>}</label>
        <label>Content<textarea aria-label="Content body" rows={10} maxLength={20000} value={draft.body} onChange={event => patch('body', event.target.value)} />{errors.body && <small role="alert">{errors.body}</small>}</label>
        <label>Status<select aria-label="Content status" value={draft.status} onChange={event => patch('status', event.target.value)}>{Object.entries(statuses).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      </fieldset>
      {error && <p className="validation-copy" role="alert">{error}</p>}
      <div className="inline-actions"><button type="button" className="secondary-button" disabled={busy} onClick={() => onNavigate('content')}>Cancel</button><button type="button" className="secondary-button" disabled={busy} onClick={() => setPreview(true)}>Preview</button><button type="submit" className="primary-button" disabled={busy || !dirty}>Save Content</button></div>
    </form>
    <ConfirmDialog open={preview} title="Content preview" hideConfirm cancelLabel="Close Preview" onCancel={() => setPreview(false)}><article className="content-preview"><h2>{draft.title || 'Untitled'}</h2><p>{draft.body}</p></article></ConfirmDialog>
  </Panel>
}

export default function ContentManagementPage({ entries, detailId, onSave, onNavigate }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const visible = entries.filter(entry => (!status || entry.status === status) && `${entry.title} ${entry.key} ${entry.body}`.toLowerCase().includes(query.trim().toLowerCase()))
  const pagination = usePagination(visible, `${query}|${status}`)
  const entry = entries.find(item => item.id === detailId)
  return <><div className="page-head"><h1>Content Management</h1>{!detailId && <button type="button" className="primary-button" onClick={() => onNavigate('content/new')}>Add Content</button>}</div>
    {detailId ? detailId === 'new' || entry ? <ContentEditor key={detailId} entry={entry} onSave={onSave} onNavigate={onNavigate} /> : <Panel><p>This content entry is unavailable.</p><button type="button" onClick={() => onNavigate('content')}>Back to Content</button></Panel> : <Panel>
      <div className="content-filters"><input type="search" aria-label="Search content" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search content" /><select aria-label="Filter content status" value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option>{Object.entries(statuses).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></div>
      <div className="content-list">{pagination.items.map(item => <article key={item.id}><div><strong>{item.title}</strong><small>{item.key} · {statuses[item.status]}</small></div><button type="button" className="secondary-button" aria-label={`Edit ${item.title}`} onClick={() => onNavigate(`content/${item.id}`)}>Edit</button></article>)}{!visible.length && <p className="empty">No matching content.</p>}</div>
      <PaginationControls {...pagination} onPage={pagination.setPage} />
    </Panel>}
  </>
}

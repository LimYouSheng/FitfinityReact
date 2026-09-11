import { useEffect, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { packageErrors, packageValidityDays } from '../../app/packages.js'

export default function PackagesPage({ packages, policy, selectedId, onNavigate, onBack, onSave }) {
  const current = packages.find(item => item.id === selectedId)
  const confirm = useActionConfirmation()
  const { activeEdit, setActiveEdit } = useEditGuard()
  const [editing, setEditing] = useState(selectedId === 'new')
  const [draft, setDraft] = useState(() => ({ name: current?.name ?? '', total: current?.total ?? '' }))
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(null)
  const pending = useRef(false)
  const pagination = usePagination([...packages].reverse(), 'packages')

  useEffect(() => {
    setActiveEdit(editing ? 'Package setup' : null)
    return () => setActiveEdit(null)
  }, [editing, setActiveEdit])
  useEffect(() => {
    if (saved && !activeEdit) {
      setSaved(null)
      onNavigate(`packages/${saved.id}`, { replace: true })
    }
  }, [activeEdit, onNavigate, saved])

  const save = async (status = current?.status ?? 'active') => {
    if (pending.current) return
    const nextErrors = packageErrors(draft, policy)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    pending.current = true
    setBusy(true)
    try {
      const action = current && status !== current.status ? (status === 'active' ? 'Reactivate Package' : 'Deactivate Package') : current ? 'Save Package' : 'Create Package'
      const accepted = await confirm({ title: `${action}?`,
        message: `${draft.name.trim()} · ${draft.total} sessions · ${packageValidityDays(draft.total, policy)} days. Existing client packages keep their purchased terms.`,
        confirmLabel: action })
      if (!accepted) return
      const result = await onSave({ id: current?.id, expectedVersion: current?.version, draft: { ...draft, total: Number(draft.total), status } })
      setEditing(false)
      setSaved(result)
    } catch (error) { setErrors({ form: error.message }) }
    finally { pending.current = false; setBusy(false) }
  }

  return <div className="package-setup">
    <div className={selectedId ? 'page-head' : 'page-head directory-page-head'}><div><span className="eyebrow">Setup</span><h1>{selectedId === 'new' ? 'New Package' : current?.name ?? 'Packages'}</h1></div>
      {!selectedId && <button className="onboarding-button primary" onClick={() => onNavigate('packages/new')}>Add Package</button>}
    </div>
    {selectedId && selectedId !== 'new' && !current ? <Panel><p>Package unavailable.</p></Panel>
      : editing ? <Panel className="editing-section">
        <form className="package-form" onSubmit={event => { event.preventDefault(); void save() }} noValidate>
          <fieldset disabled={busy} className="package-fields">
            <label className="package-required">Package name <span>Required</span><input aria-label="Package name" required maxLength={80} value={draft.name} aria-invalid={Boolean(errors.name)} onChange={event => setDraft(value => ({ ...value, name: event.target.value }))} />{errors.name && <small>{errors.name}</small>}</label>
            <label className="package-required">Session count <span>Required</span><input aria-label="Package session count" type="text" inputMode="numeric" pattern="[0-9]*" required value={draft.total} aria-invalid={Boolean(errors.total)} aria-describedby={errors.total ? 'package-count-error' : undefined} onChange={event => setDraft(value => ({ ...value, total: event.target.value }))} />{errors.total && <small id="package-count-error">{errors.total}</small>}</label>
          </fieldset>
          <div className="inline-actions"><button type="button" className="onboarding-button" disabled={busy} onClick={() => { if (current) { setEditing(false); setDraft({ name: current.name, total: current.total }) } else onBack() }}>Cancel</button><button className="onboarding-button primary" type="submit" disabled={busy}>{current ? 'Save Package' : 'Create Package'}</button></div>
          {errors.form && <p className="validation-copy" role="alert">{errors.form}</p>}
        </form>
      </Panel> : current ? <Panel>
        <div className="section-head"><h2>Package details</h2><StatusBadge tone={current.status === 'active' ? 'green' : 'amber'}>{current.status === 'active' ? 'Active' : 'Inactive'}</StatusBadge></div>
        <dl className="package-details"><div><dt>Sessions</dt><dd>{current.total}</dd></div><div><dt>Validity</dt><dd>{current.validityDays} days</dd></div></dl>
        <div className="inline-actions"><button className="onboarding-button" onClick={() => { setSaved(null); setDraft({ name: current.name, total: current.total }); setEditing(true) }}>Edit Package</button><button className="onboarding-button" disabled={busy} onClick={() => void save(current.status === 'active' ? 'inactive' : 'active')}>{current.status === 'active' ? 'Deactivate Package' : 'Reactivate Package'}</button></div>
        {errors.form && <p className="validation-copy" role="alert">{errors.form}</p>}
      </Panel> : <Panel><div className="package-list" aria-label="Package list">{pagination.items.map(item => <div className="package-row" key={item.id}>
        <div><strong>{item.name}</strong><span>{item.total} sessions · {item.validityDays} days</span></div><StatusBadge tone={item.status === 'active' ? 'green' : 'amber'}>{item.status === 'active' ? 'Active' : 'Inactive'}</StatusBadge><button className="secondary-button small" aria-label={`View package ${item.name}`} onClick={() => onNavigate(`packages/${item.id}`)}>View</button>
      </div>)}</div><PaginationControls {...pagination} onPage={pagination.setPage} /></Panel>}
  </div>
}

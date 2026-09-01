import { useEffect, useState } from 'react'
import { APPROVAL_FIELDS } from '../../app/constants.js'
import ApprovalSetting from '../../components/ApprovalSetting.jsx'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'

export default function TrainerProfilePage({ trainer, onBack, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(trainer.approvalNeeded)
  useEffect(() => setDraft(trainer.approvalNeeded), [trainer])
  const supervised = Object.values(trainer.approvalNeeded).filter(Boolean).length
  const save = () => { onSave(draft); setEditing(false) }
  return (
    <>
      <div className="page-head"><div><button type="button" className="back-link" onClick={onBack}>← Trainers</button><span className="eyebrow">Trainer profile</span><h1>{trainer.name}</h1><p>{trainer.specialty}</p></div><StatusBadge tone={supervised ? 'amber' : 'green'}>{supervised ? `${supervised} approval controls` : 'Fully autonomous'}</StatusBadge></div>
      <div className="two-column">
        <Panel><div className="section-head"><h2>General Information</h2></div><div className="info-list"><div className="info-row"><span>Email</span><strong>{trainer.email}</strong></div><div className="info-row"><span>Phone</span><strong>{trainer.phone}</strong></div><div className="info-row"><span>Specialty</span><strong>{trainer.specialty}</strong></div></div></Panel>
        <Panel>
          <div className="section-head"><div><h2>Owner Approval Needed</h2><p>Checked = trainer must submit a request.</p></div>{!editing ? <button type="button" className="text-action" onClick={() => setEditing(true)}>Edit</button> : <div className="inline-actions"><button type="button" className="text-action muted-action" onClick={() => { setDraft(trainer.approvalNeeded); setEditing(false) }}>Cancel</button><button type="button" className="text-action" onClick={save}>Save</button></div>}</div>
          <div className="approval-grid">
            {APPROVAL_FIELDS.map(([field,label]) => <ApprovalSetting key={field} label={label} checked={(editing ? draft : trainer.approvalNeeded)[field]} disabled={!editing} onChange={checked => setDraft(current => ({ ...current, [field]: checked }))} />)}
          </div>
          <p className="helper">Uncheck and save = that change is allowed directly. This deliberately matches the final v0.57 checkbox semantics.</p>
        </Panel>
      </div>
    </>
  )
}

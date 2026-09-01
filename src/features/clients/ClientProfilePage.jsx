import { useEffect, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import FixedWeeklySchedule from './FixedWeeklySchedule.jsx'
import { canEditClientCoachingNotes, canEditClientGeneral } from '../../app/permissions.js'
import { formatDate, packageDayProgress } from '../../utils/date.js'

function EditableText({ title, value, editable, multiline = false, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  const save = () => { onSave(draft); setEditing(false) }
  return (
    <Panel>
      <div className="section-head"><h2>{title}</h2>{editable && (!editing ? <button type="button" className="text-action" onClick={() => setEditing(true)}>Edit</button> : <div className="inline-actions"><button type="button" className="text-action muted-action" onClick={() => { setDraft(value); setEditing(false) }}>Cancel</button><button type="button" className="text-action" onClick={save}>Save</button></div>)}</div>
      {editing ? (multiline ? <textarea value={draft} onChange={event => setDraft(event.target.value)} /> : <input value={draft} onChange={event => setDraft(event.target.value)} />) : <div className="notice">{value}</div>}
    </Panel>
  )
}

export default function ClientProfilePage({ user, client, trainer, onBack, onUpdate }) {
  const [editingGeneral, setEditingGeneral] = useState(false)
  const [draft, setDraft] = useState(client)
  useEffect(() => setDraft(client), [client])
  const ownerEditable = canEditClientGeneral(user)
  const notesEditable = canEditClientCoachingNotes(user, client)
  const progress = packageDayProgress(client.package.startDate, client.package.validityDays)
  const saveGeneral = () => { onUpdate({ phone: draft.phone, email: draft.email, birthday: draft.birthday, gender: draft.gender, emergencyContact: draft.emergencyContact }); setEditingGeneral(false) }
  return (
    <>
      <div className="page-head"><div><button type="button" className="back-link" onClick={onBack}>← Clients</button><span className="eyebrow">Client profile</span><h1>{client.name}</h1><p>{client.type} • Trainer: {trainer?.name ?? '—'}</p></div><StatusBadge tone="green">Active</StatusBadge></div>
      <div className="profile-tabs"><button className="active" type="button">Overview</button><button type="button" disabled>Package</button><button type="button" disabled>Session History</button><button type="button" disabled>Upcoming Sessions</button><button type="button" disabled>Progress</button></div>

      <div className="two-column">
        <Panel>
          <div className="section-head"><h2>General Information</h2>{ownerEditable && (!editingGeneral ? <button type="button" className="text-action" onClick={() => setEditingGeneral(true)}>Edit</button> : <div className="inline-actions"><button type="button" className="text-action muted-action" onClick={() => { setDraft(client); setEditingGeneral(false) }}>Cancel</button><button type="button" className="text-action" onClick={saveGeneral}>Save</button></div>)}</div>
          <div className="info-list">
            {[['Phone','phone','text'],['Email','email','email'],['Birthday','birthday','date'],['Gender','gender','text'],['Emergency contact','emergencyContact','text']].map(([label,key,type]) => <div className="info-row" key={key}><span>{label}</span>{editingGeneral ? <input aria-label={label} type={type} value={draft[key]} onChange={event => setDraft(current => ({ ...current, [key]: event.target.value }))} /> : <strong>{key === 'birthday' ? formatDate(client[key]) : client[key]}</strong>}</div>)}
            <div className="info-row"><span>Start date</span><strong>{formatDate(client.startDate)}</strong></div>
            <div className="info-row"><span>Trainer</span><strong>{trainer?.name ?? '—'}</strong></div>
            <div className="info-row"><span>Package validity</span><strong>{progress} / {client.package.validityDays} days</strong></div>
            <div className="info-row"><span>Trainer preference</span><strong>{client.trainerPreference}</strong></div>
          </div>
        </Panel>
        <FixedWeeklySchedule slots={client.fixedWeeklySchedule} editable={ownerEditable} onSave={slots => onUpdate({ fixedWeeklySchedule: slots })} />
      </div>

      <div className="stack-gap">
        <EditableText title="Health / Limitation Notes" value={client.healthNotes} editable={notesEditable} multiline onSave={healthNotes => onUpdate({ healthNotes })} />
        <EditableText title="Remarks" value={client.remarks} editable={notesEditable} multiline onSave={remarks => onUpdate({ remarks })} />
      </div>
    </>
  )
}

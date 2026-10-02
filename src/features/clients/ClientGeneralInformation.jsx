import { useEffect, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import ClientGeneralFields from './ClientGeneralFields.jsx'
import { clientProfileDraft, clientStepErrors } from '../../app/clientOnboarding.js'
import { formatDate } from '../../utils/date.js'

function displayPhone(phone) {
  if (!phone) return '—'
  return typeof phone === 'string' ? phone : `${phone.countryCode} ${phone.number}`.trim()
}

function displayEmergency(contact) {
  if (!contact) return '—'
  if (typeof contact === 'string') return contact
  return [contact.name, contact.relationship, displayPhone(contact)].filter(Boolean).join(' · ')
}

export default function ClientGeneralInformation({ client, trainer, policy, ownerEditable, activeEditor, setActiveEditor, onUpdate }) {
  const confirmAction = useActionConfirmation()
  const [draft, setDraft] = useState(() => clientProfileDraft(client, policy))
  const [activePerson, setActivePerson] = useState(0)
  const [generalErrors, setGeneralErrors] = useState({})
  const generalFields = useRef(null)

  const draftIdentity = useRef({ id: client.id, status: client.status })
  useEffect(() => {
    const changed = draftIdentity.current.id !== client.id || draftIdentity.current.status !== client.status
    // Refresh read-only values; an ordinary snapshot refresh must preserve edits.
    if (changed || !activeEditor) setDraft(clientProfileDraft(client, policy))
    draftIdentity.current = { id: client.id, status: client.status }
  }, [activeEditor, client, policy])

  const saveGeneral = async () => {
    const errors = clientStepErrors(draft, 'general', { requireComplete: false })
    if (Object.keys(errors).length) {
      setGeneralErrors(errors)
      setActivePerson(Number(Object.keys(errors)[0].split('.')[1]) || 0)
      return
    }
    const confirmed = await confirmAction({
      title: 'Save client information?',
      message: 'This will update the client’s contact and personal information.',
      confirmLabel: 'Save Changes',
    })
    if (!confirmed) return
    try {
      await onUpdate({
        people: draft.people,
        remarks: draft.remarks,
        genderPreference: draft.genderPreference,
      })
      setActiveEditor(null)
    } catch (error) { setGeneralErrors({ save: error.message || 'Client information could not be saved.' }) }
  }

  useEffect(() => {
    if (Object.keys(generalErrors).length) generalFields.current?.querySelector('[aria-invalid="true"]')?.focus()
  }, [generalErrors, activePerson])

  return (
    <Panel className={activeEditor === 'general' ? 'editing-section' : ''}>
      <div className="section-head">
        <h2>General Information</h2>

        {ownerEditable && (activeEditor !== 'general' ? (
          <button
            type="button"
            className="text-action"
            disabled={Boolean(activeEditor)}
            onClick={() => { setGeneralErrors({}); setActivePerson(0); setActiveEditor('general') }}
          >
            Edit
          </button>
        ) : (
          <div className="inline-actions">
            <button
              type="button"
              className="text-action muted-action"
              onClick={() => {
                setDraft(clientProfileDraft(client, policy))
                setActiveEditor(null)
              }}
            >
              Cancel
            </button>
            <button type="button" className="text-action" onClick={saveGeneral}>Save</button>
          </div>
        ))}
      </div>

      {activeEditor === 'general' ? <div ref={generalFields}>
        {client.type === 'Couple' && client.people?.length !== 2 && <p className="helper">This older couple profile has one combined record. Review both clients’ names and details before saving.</p>}
        <ClientGeneralFields editing draft={draft} errors={generalErrors} activePerson={activePerson} setActivePerson={setActivePerson}
          onChange={patch => { setDraft(current => ({ ...current, ...patch })); setGeneralErrors({}) }} />
        {generalErrors.save && <p role="alert">{generalErrors.save}</p>}
      </div> : <div className="info-list profile-info-grid">
        <div className="info-row"><span>Name</span><strong>{client.name}</strong></div>
        <div className="info-row"><span>Phone</span><strong>{displayPhone(client.phone)}</strong></div>
        {[['Email', 'email'], ['Birthday', 'birthday'], ['Gender', 'gender']].map(([label, key]) => (
          <div className="info-row" key={key}><span>{label}</span><strong>{key === 'birthday' ? formatDate(client[key]) : client[key]}</strong></div>
        ))}
        <div className="info-row emergency-contact-row"><span>Emergency contact</span><strong>{displayEmergency(client.emergencyContact)}</strong></div>
        <div className="info-row"><span>Gender preference</span><strong>{client.genderPreference}</strong></div>

        <div className="info-row">
          <span>Start date</span>
          <strong>{formatDate(client.startDate)}</strong>
        </div>

        <div className="info-row client-trainer-row">
          <span>Trainer</span>
          <div className="client-trainer-assignment"><strong>{trainer?.name ?? '—'}</strong>
            {ownerEditable && <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => setActiveEditor('trainer')}>Reassign Trainer</button>}
          </div>
        </div>

      </div>}
    </Panel>

  )
}

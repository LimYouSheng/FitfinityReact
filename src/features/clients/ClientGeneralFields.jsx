import SelectField from '../../components/SelectField.jsx'
import Field from '../../components/OnboardingField.jsx'
import ClientPersonFields from './ClientPersonFields.jsx'
import { GENDER_PREFERENCES } from '../../app/contact.js'

/** Shared personal fields for creation and profile editing; purchased client type is fixed on edit. */
export default function ClientGeneralFields({ draft, errors = {}, activePerson, setActivePerson, onChange, editing = false }) {
  const update = onChange
  const personLabel = draft.type === 'Couple' ? `Client ${activePerson + 1}` : 'Client'
  const updatePerson = nextPerson => update({ people: draft.people.map((person, index) => index === activePerson ? nextPerson : person) })
  return (
    <div className="onboarding-general-fields">
      <Field label="Client type" required error={errors.type}>
        <SelectField aria-label="Client type" disabled={editing} value={draft.type} onChange={event => { update({ type: event.target.value }); setActivePerson(0) }}>
          <option value="Individual">Single</option><option value="Couple">Couple</option>
        </SelectField>
      </Field>
      {draft.type === 'Couple' && (
        <div className="onboarding-person-tabs" role="group" aria-label="Couple client tabs">
          {[0, 1].map(index => (
            <button key={index} type="button" className={activePerson === index ? 'active' : ''} aria-pressed={activePerson === index} onClick={() => setActivePerson(index)}>
              Client {index + 1}
            </button>
          ))}
        </div>
      )}
      <ClientPersonFields person={draft.people[activePerson]} labelPrefix={personLabel} requireComplete={!editing} errors={Object.fromEntries(Object.entries(errors).filter(([key]) => key.startsWith(`people.${activePerson}.`)).map(([key, value]) => [key.split('.').slice(2).join('.'), value]))} onChange={updatePerson} />
      <Field label="Remarks"><textarea aria-label="Remarks" value={draft.remarks} onChange={event => update({ remarks: event.target.value })} /></Field>
      {editing && <Field label="Gender preference"><SelectField aria-label="Gender preference" value={draft.genderPreference}
        onChange={event => update({ genderPreference: event.target.value })}>
        {GENDER_PREFERENCES.map(preference => <option key={preference}>{preference}</option>)}
      </SelectField></Field>}
    </div>
  )
}

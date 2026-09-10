import Field from '../../components/OnboardingField.jsx'
import { COUNTRY_CODES, RELATIONSHIPS, GENDERS } from '../../app/contact.js'

export default function ClientPersonFields({ person, labelPrefix, nameError, genderError, onChange }) {
  const patch = next => onChange({ ...person, ...next })

  return (
    <div className="onboarding-grid">
      <Field label={`${labelPrefix} name`} required error={nameError} className="onboarding-span-2">
        <input aria-label={`${labelPrefix} name`} value={person.name} onChange={event => patch({ name: event.target.value })} />
      </Field>

      <Field label="Phone" group>
        <div className="onboarding-phone-grid">
          <select
            aria-label={`${labelPrefix} phone country code`}
            value={person.phone.countryCode}
            onChange={event => patch({ phone: { ...person.phone, countryCode: event.target.value } })}
          >
            {COUNTRY_CODES.map(code => <option key={code}>{code}</option>)}
          </select>
          <input
            aria-label={`${labelPrefix} phone number`}
            inputMode="tel"
            value={person.phone.number}
            onChange={event => patch({ phone: { ...person.phone, number: event.target.value } })}
          />
        </div>
      </Field>

      <Field label="Email">
        <input aria-label={`${labelPrefix} email`} type="email" value={person.email} onChange={event => patch({ email: event.target.value })} />
      </Field>

      <Field label="Birthday">
        <input aria-label={`${labelPrefix} birthday`} type="date" value={person.birthday} onChange={event => patch({ birthday: event.target.value })} />
      </Field>

      <Field label="Gender" error={genderError}>
        <select aria-label={`${labelPrefix} gender`} value={person.gender} onChange={event => patch({ gender: event.target.value })}>
          <option value="">Select gender</option>
          {GENDERS.map(gender => <option key={gender}>{gender}</option>)}
        </select>
      </Field>

      <Field label="Emergency contact" group className="onboarding-span-2">
        <div className="onboarding-emergency-grid">
          <input
            aria-label={`${labelPrefix} emergency contact name`}
            placeholder="Name"
            value={person.emergencyContact.name}
            onChange={event => patch({ emergencyContact: { ...person.emergencyContact, name: event.target.value } })}
          />
          <select
            aria-label={`${labelPrefix} emergency contact relationship`}
            value={person.emergencyContact.relationship}
            onChange={event => patch({ emergencyContact: { ...person.emergencyContact, relationship: event.target.value } })}
          >
            {RELATIONSHIPS.map(relationship => <option key={relationship}>{relationship}</option>)}
          </select>
          <select
            aria-label={`${labelPrefix} emergency contact country code`}
            value={person.emergencyContact.countryCode}
            onChange={event => patch({ emergencyContact: { ...person.emergencyContact, countryCode: event.target.value } })}
          >
            {COUNTRY_CODES.map(code => <option key={code}>{code}</option>)}
          </select>
          <input
            aria-label={`${labelPrefix} emergency contact phone number`}
            inputMode="tel"
            placeholder="Phone"
            value={person.emergencyContact.number}
            onChange={event => patch({ emergencyContact: { ...person.emergencyContact, number: event.target.value } })}
          />
        </div>
      </Field>

      <Field label="Health / Limitation Notes" className="onboarding-span-2">
        <textarea
          aria-label={`${labelPrefix} health or limitation notes`}
          value={person.healthNotes}
          onChange={event => patch({ healthNotes: event.target.value })}
          placeholder="Optional"
        />
      </Field>
    </div>
  )
}

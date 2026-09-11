import DateField from '../../components/DateField.jsx'
import SelectField from '../../components/SelectField.jsx'
import Field from '../../components/OnboardingField.jsx'
import { COUNTRY_CODES, RELATIONSHIPS, GENDERS } from '../../app/contact.js'

export default function ClientPersonFields({ person, labelPrefix, errors = {}, requireComplete = false, onChange }) {
  const patch = next => onChange({ ...person, ...next })

  return (
    <div className="onboarding-grid">
      <Field label={`${labelPrefix} name`} required error={errors.name} className="onboarding-span-2">
        <input aria-label={`${labelPrefix} name`} value={person.name} onChange={event => patch({ name: event.target.value })} />
      </Field>

      <Field label="Phone" required={requireComplete} group error={errors.phoneCountryCode || errors.phoneNumber}>
        <div className="onboarding-phone-grid">
          <SelectField
            aria-label={`${labelPrefix} phone country code`}
            required={requireComplete} aria-required={requireComplete || undefined} aria-invalid={Boolean(errors.phoneCountryCode)}
            value={person.phone.countryCode}
            onChange={event => patch({ phone: { ...person.phone, countryCode: event.target.value } })}
          >
            {COUNTRY_CODES.map(code => <option key={code}>{code}</option>)}
          </SelectField>
          <input
            aria-label={`${labelPrefix} phone number`}
            required={requireComplete} aria-required={requireComplete || undefined} aria-invalid={Boolean(errors.phoneNumber)}
            inputMode="tel"
            value={person.phone.number}
            onChange={event => patch({ phone: { ...person.phone, number: event.target.value } })}
          />
        </div>
      </Field>

      <Field label="Email" required={requireComplete} error={errors.email}>
        <input aria-label={`${labelPrefix} email`} type="email" value={person.email} onChange={event => patch({ email: event.target.value })} />
      </Field>

      <Field label="Birthday" required={requireComplete} error={errors.birthday}>
        <DateField aria-label={`${labelPrefix} birthday`}  value={person.birthday} onChange={event => patch({ birthday: event.target.value })} />
      </Field>

      <Field label="Gender" required={requireComplete} error={errors.gender}>
        <SelectField aria-label={`${labelPrefix} gender`} value={person.gender} onChange={event => patch({ gender: event.target.value })}>
          <option value="">Select gender</option>
          {GENDERS.map(gender => <option key={gender}>{gender}</option>)}
        </SelectField>
      </Field>

      <Field label="Emergency contact" required={requireComplete} group error={errors.emergencyName || errors.emergencyRelationship || errors.emergencyCountryCode || errors.emergencyNumber} className="onboarding-span-2">
        <div className="onboarding-emergency-grid">
          <input
            aria-label={`${labelPrefix} emergency contact name`}
            required={requireComplete} aria-required={requireComplete || undefined} aria-invalid={Boolean(errors.emergencyName)}
            placeholder="Name"
            value={person.emergencyContact.name}
            onChange={event => patch({ emergencyContact: { ...person.emergencyContact, name: event.target.value } })}
          />
          <SelectField
            aria-label={`${labelPrefix} emergency contact relationship`}
            required={requireComplete} aria-required={requireComplete || undefined} aria-invalid={Boolean(errors.emergencyRelationship)}
            value={person.emergencyContact.relationship}
            onChange={event => patch({ emergencyContact: { ...person.emergencyContact, relationship: event.target.value } })}
          >
            {RELATIONSHIPS.map(relationship => <option key={relationship}>{relationship}</option>)}
          </SelectField>
          <SelectField
            aria-label={`${labelPrefix} emergency contact country code`}
            required={requireComplete} aria-required={requireComplete || undefined} aria-invalid={Boolean(errors.emergencyCountryCode)}
            value={person.emergencyContact.countryCode}
            onChange={event => patch({ emergencyContact: { ...person.emergencyContact, countryCode: event.target.value } })}
          >
            {COUNTRY_CODES.map(code => <option key={code}>{code}</option>)}
          </SelectField>
          <input
            aria-label={`${labelPrefix} emergency contact phone number`}
            required={requireComplete} aria-required={requireComplete || undefined} aria-invalid={Boolean(errors.emergencyNumber)}
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

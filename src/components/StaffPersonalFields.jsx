import DateField from './DateField.jsx'
import SelectField from './SelectField.jsx'
import Field from './OnboardingField.jsx'
import { COUNTRY_CODES, GENDERS } from '../app/contact.js'

/** Shared personal information controls; role-specific fields belong to their owning form. */
export default function StaffPersonalFields({ draft, errors = {}, onChange: update, label = 'Staff', requireComplete = true }) {
  return <>
    <Field label={`${label} name`} required error={errors.name}>
      <input aria-label={`${label} name`} autoComplete="name" maxLength={200} value={draft.name} onChange={event => update({ name: event.target.value })} />
    </Field>
    <Field label="Email" required error={errors.email}>
      <input aria-label={`${label} email`} type="email" autoComplete="email" maxLength={320} value={draft.email} onChange={event => update({ email: event.target.value })} />
    </Field>
    <Field label="Phone" required={requireComplete} group error={errors.phoneCountryCode || errors.phoneNumber}>
      <div className="onboarding-phone-grid">
        <SelectField aria-label={`${label} phone country code`} required={requireComplete} aria-required={requireComplete || undefined} value={draft.phone.countryCode} aria-invalid={Boolean(errors.phoneCountryCode)} onChange={event => update({ phone: { ...draft.phone, countryCode: event.target.value } })}>
          {COUNTRY_CODES.map(code => <option key={code}>{code}</option>)}
        </SelectField>
        <input aria-label={`${label} phone number`} required={requireComplete} aria-required={requireComplete || undefined} inputMode="tel" maxLength={32} aria-invalid={Boolean(errors.phoneNumber)} value={draft.phone.number} onChange={event => update({ phone: { ...draft.phone, number: event.target.value } })} />
      </div>
    </Field>
    <Field label="Birthday" required={requireComplete} error={errors.birthday}>
      <DateField aria-label={`${label} birthday`} value={draft.birthday} onChange={event => update({ birthday: event.target.value })} />
    </Field>
    <Field label="Gender" required error={errors.gender}>
      <SelectField aria-label={`${label} gender`} value={draft.gender} onChange={event => update({ gender: event.target.value })}>
        <option value="">Select gender</option>{GENDERS.map(gender => <option key={gender}>{gender}</option>)}
      </SelectField>
    </Field>
  </>
}

import { COUNTRY_CODES, GENDERS, validPhoneNumber } from './contact.js'

export const createAdminDraft = () => ({ name: '', email: '', phone: { countryCode: '+65', number: '' }, birthday: '', gender: '' })

// One in-memory workflow per verified Owner session. Directory views may unmount;
// retiring the session or deliberately leaving the workflow invalidates late writes.
export function createAdminCreationState(ownerId) {
  const empty = () => ({ draft: createAdminDraft(), errors: {}, saving: false, submitted: false, created: null, requestKey: null })
  let state = empty(), version = 0, retired = false
  const listeners = new Set()
  const publish = () => listeners.forEach(listener => listener())
  return {
    ownerId,
    getSnapshot: () => state,
    subscribe: listener => { listeners.add(listener); return () => listeners.delete(listener) },
    version: () => version,
    update(patch, expectedVersion = version) {
      if (retired || expectedVersion !== version) return false
      state = { ...state, ...patch }; publish(); return true
    },
    reset() { version++; state = empty(); publish() },
    retire() { retired = true; version++; state = empty(); publish() },
  }
}

export function adminErrors(draft, today) {
  const errors = {}
  if (!draft.name.trim() || draft.name.trim().length > 200) errors.name = 'Enter the staff name.'
  if (draft.email.length > 320 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.email.trim())) errors.email = 'Enter a valid email address.'
  if (!COUNTRY_CODES.includes(draft.phone.countryCode)) errors.phoneCountryCode = 'Choose a phone country code.'
  if (!validPhoneNumber(draft.phone)) errors.phoneNumber = 'Enter a valid phone number.'
  const parsed = new Date(`${draft.birthday}T00:00:00Z`)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.birthday) || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== draft.birthday || draft.birthday > today) errors.birthday = 'Choose a valid birthday that is not in the future.'
  if (!GENDERS.includes(draft.gender)) errors.gender = 'Choose a gender.'
  return errors
}

export function adminPayload(draft) {
  return { name: draft.name.trim(), email: draft.email.trim().toLowerCase(), phone_country_code: draft.phone.countryCode,
    phone_number: draft.phone.number.trim(), birthday: draft.birthday, gender: draft.gender }
}

export const COUNTRY_CODES = ['+65', '+60', '+62', '+63', '+66', '+84', '+86', '+91', '+44', '+61']
export const RELATIONSHIPS = ['Spouse', 'Parent', 'Sibling', 'Child', 'Partner', 'Friend', 'Guardian', 'Other']
export const GENDER_PREFERENCES = ['No gender preference', 'Female trainer preferred', 'Male trainer preferred']
export const GENDERS = ['Female', 'Male', 'Other', 'Prefer not to say']

export function phoneDraft(value, defaultCountryCode) {
  if (value && typeof value === 'object') return { countryCode: value.countryCode ?? defaultCountryCode, number: value.number ?? '' }
  const phone = typeof value === 'string' ? value.trim() : ''
  const code = [...COUNTRY_CODES].sort((a, b) => b.length - a.length).find(item => phone.startsWith(item))
  return { countryCode: code ?? defaultCountryCode, number: code ? phone.slice(code.length).trim() : phone }
}

export function validPhoneNumber(phone) {
  const number = typeof phone?.number === 'string' ? phone.number.trim() : ''
  return /^[\d\s()-]+$/.test(number) && number.replace(/\D/g, '').length >= 6 &&
    (String(phone?.countryCode ?? '').replace(/\D/g, '') + number.replace(/\D/g, '')).length <= 15
}

export function phoneText(phone) {
  const number = typeof phone?.number === 'string' ? phone.number.trim() : ''
  return number ? `${phone.countryCode} ${number}` : ''
}

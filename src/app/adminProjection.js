const protectedFields = new Set(['rates', 'trainerRates', 'rateCents', 'amountCents', 'peak_rate_cents', 'off_peak_rate_cents'])
export const adminMessageAllowed = message => message.category !== 'remuneration' && !message.remunerationCycle && !message.kind?.startsWith('remuneration') && message.kind !== 'trainer_rates'

/** Demo adapter mirrors the server's financial boundary. Live API responses are allowlisted there. */
export function adminProjection(value) {
  if (Array.isArray(value)) return value.map(adminProjection)
  if (!value || typeof value !== 'object') return value
  if (value instanceof Blob) return value
  return Object.fromEntries(Object.entries(value)
    .filter(([key]) => !protectedFields.has(key) && !key.startsWith('remuneration'))
    .map(([key, item]) => [key, key === 'messages' && Array.isArray(item) ? item.filter(adminMessageAllowed).map(adminProjection) : adminProjection(item)]))
}

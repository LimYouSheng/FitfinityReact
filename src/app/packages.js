export const freeGymEligible = (frequency, minimum) => Number.isFinite(minimum) && Number(frequency) >= minimum
export const weeklyFrequencyLabel = (frequency, compact = false) =>
  `${Number(frequency) === 1 ? 'Once' : Number(frequency) === 2 ? 'Twice' : `${frequency} times`} ${compact ? 'weekly' : 'per week'}`

export const packageDefinitions = data => data.packages ?? []
export const activePackages = data => packageDefinitions(data).filter(item => item.status === 'active')

export function packageValidityDays(total, policy) {
  const configured = policy.packageValidity?.[Number(total)]
  if (Number.isInteger(configured) && configured > 0) return configured
  const { sessions, days } = policy.packageValidityRule ?? {}
  if (!(sessions > 0 && days > 0)) throw new Error('Package validity settings are unavailable.')
  return Math.ceil(Number(total) * days / sessions)
}

export function packageErrors(draft, policy) {
  const errors = {}
  if (typeof draft.name !== 'string' || !draft.name.trim()) errors.name = 'Package name is required.'
  else if (draft.name.trim().length > 80) errors.name = 'Use 80 characters or fewer.'
  const { minimum, maximum } = policy.packageSessionCount
  if (!/^\d+$/.test(String(draft.total)) || !Number.isSafeInteger(Number(draft.total)) || Number(draft.total) < minimum || Number(draft.total) > maximum) errors.total = `Enter a whole number from ${minimum} to ${maximum}.`
  return errors
}

export function selectedPackage(data, draft) {
  const packages = packageDefinitions(data)
  const item = draft.packageId ? packages.find(item => item.id === draft.packageId)
    : null
  if (!item || item.status !== 'active') throw new Error('Choose an active PT package.')
  if (draft.packageVersion != null && draft.packageVersion !== item.version) throw new Error('Package changed. Reopen client creation to review the latest package.')
  return item
}

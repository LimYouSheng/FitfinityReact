export const freeGymEligible = (frequency, minimum) => Number.isFinite(minimum) && Number(frequency) >= minimum
export const weeklyFrequencyLabel = (frequency, compact = false) =>
  `${Number(frequency) === 1 ? 'Once' : Number(frequency) === 2 ? 'Twice' : `${frequency} times`} ${compact ? 'weekly' : 'per week'}`

export const packageDefinitions = data => data.packages ?? []
export const activePackages = data => packageDefinitions(data).filter(item => item.status === 'active')

export function packageErrors(draft, validity = {}) {
  const errors = {}
  if (typeof draft.name !== 'string' || !draft.name.trim()) errors.name = 'Package name is required.'
  else if (draft.name.trim().length > 80) errors.name = 'Use 80 characters or fewer.'
  if (!Object.hasOwn(validity, Number(draft.total))) errors.total = 'Choose an available session count.'
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

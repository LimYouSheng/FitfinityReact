export const PACKAGE_VALIDITY = Object.freeze({ 12: 90, 24: 180, 36: 270 })
export const WEEKLY_FREQUENCIES = [1, 2, 3, 4, 5, 6, 7]
export const DEFAULT_PACKAGES = Object.keys(PACKAGE_VALIDITY).map(value => ({
  id: `package-${value}`, name: `${value} sessions`, total: Number(value),
  validityDays: PACKAGE_VALIDITY[value], status: 'active', version: 1,
}))
export const freeGymEligible = frequency => Number(frequency) >= 2
export const weeklyFrequencyLabel = (frequency, compact = false) =>
  `${Number(frequency) === 1 ? 'Once' : Number(frequency) === 2 ? 'Twice' : `${frequency} times`} ${compact ? 'weekly' : 'per week'}`

export const packageDefinitions = data => data.packages ?? DEFAULT_PACKAGES
export const activePackages = data => packageDefinitions(data).filter(item => item.status === 'active')

export function packageErrors(draft) {
  const errors = {}
  if (typeof draft.name !== 'string' || !draft.name.trim()) errors.name = 'Package name is required.'
  else if (draft.name.trim().length > 80) errors.name = 'Use 80 characters or fewer.'
  if (!Object.hasOwn(PACKAGE_VALIDITY, Number(draft.total))) errors.total = 'Choose 12, 24 or 36 sessions.'
  return errors
}

export function selectedPackage(data, draft) {
  const packages = packageDefinitions(data)
  const item = draft.packageId ? packages.find(item => item.id === draft.packageId)
    : packages.find(item => item.status === 'active' && item.total === 12)
  if (!item || item.status !== 'active') throw new Error('Choose an active PT package.')
  if (draft.packageVersion != null && draft.packageVersion !== item.version) throw new Error('Package changed. Reopen client creation to review the latest package.')
  return item
}

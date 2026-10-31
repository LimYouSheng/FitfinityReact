import { businessClock } from './clock.js'

export const managesOperations = user => ['owner', 'admin'].includes(user?.role)
export const canViewTrainerRates = user => ['owner', 'trainer'].includes(user?.role)
export const canEditTrainerRates = user => user?.role === 'owner'
export const canViewRemuneration = user => ['owner', 'trainer'].includes(user?.role)
export const staffRoleLabel = user => ({ owner: 'Owner', admin: 'Admin', trainer: 'Trainer' })[user?.role] ?? 'Staff'

export function directChangeAllowed(approvalNeeded) {
  return !approvalNeeded
}

export function canEditClientGeneral(user, client) {
  return client?.status !== 'inactive' && managesOperations(user)
}

export function canEditClientCoachingNotes(user, client) {
  if (client.status === 'inactive') return false
  if (managesOperations(user)) return true
  if (user?.role !== 'trainer' || !user.trainerId) return false
  const today = businessClock().date
  return client.trainerId === user.trainerId || (client.additionalPackages ?? []).some(purchased =>
    purchased.trainerId === user.trainerId && purchased.status !== 'inactive' && purchased.startDate <= today && purchased.endDate >= today)
}

export function routeTrainerChange(approvalSettings, field) {
  return approvalSettings[field] ? 'request' : 'direct'
}

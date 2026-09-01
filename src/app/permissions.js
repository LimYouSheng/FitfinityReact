export function directChangeAllowed(approvalNeeded) {
  return !approvalNeeded
}

export function canEditClientGeneral(user) {
  return user.role === 'owner'
}

export function canEditClientCoachingNotes(user, client) {
  return user.role === 'owner' || client.trainerId === user.trainerId
}

export function routeTrainerChange(approvalSettings, field) {
  return approvalSettings[field] ? 'request' : 'direct'
}

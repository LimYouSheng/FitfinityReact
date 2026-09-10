import { addDays, buildClientSessions, clientStepErrors, packageFor, trainerCoversBlock } from './clientOnboarding.js'
import { GENDER_PREFERENCES } from './contact.js'
import { clientPackages, requireActiveClient, sessionIsInactive } from './clientPackages.js'
import { selectedPackage } from './packages.js'

/** The saved weekly schedule remains authoritative when opening a new purchase. */
export function packageDraftForClient(client, sessions, packages, today) {
  const lastDate = clientPackages(client).filter(item => item.status !== 'inactive').map(item => item.endDate).sort().at(-1)
  const minimumStartDate = lastDate ? [today, addDays(lastDate, 1)].sort().at(-1) : today
  const firstScheduled = buildClientSessions({ ...client, package: { ...client.package, startDate: minimumStartDate, total: 1, validityDays: 7 } })[0]
  const clientPreferences = structuredClone(client.clientPreferences ?? [])
  for (const slot of client.fixedWeeklySchedule ?? []) {
    if (!clientPreferences.some(block => block.days.includes(slot.day) && block.from <= slot.from && slot.to <= block.to)) {
      clientPreferences.push({ id: `saved-${slot.id}`, days: [slot.day], from: slot.from, to: slot.to })
    }
  }
  const active = packages.filter(item => item.status === 'active')
  const template = active.find(item => item.id === client.package.templateId)
  const legacyMatches = client.package.templateId ? [] : active.filter(item => item.total === client.package.total)
  const matchingTerms = legacyMatches.filter(item => item.validityDays === client.package.validityDays)
  const legacyTemplate = legacyMatches.length === 1 ? legacyMatches[0] : matchingTerms.length === 1 ? matchingTerms[0] : null
  return {
    clientName: client.name,
    packageId: template?.id ?? legacyTemplate?.id ?? '',
    startDate: firstScheduled?.date ?? minimumStartDate,
    minimumStartDate,
    sessionsPerWeek: client.package.sessionsPerWeek,
    genderPreference: client.genderPreference,
    clientPreferences,
    trainerId: client.trainerId,
    fixedWeeklySchedule: structuredClone(client.fixedWeeklySchedule),
    expectedPackageId: client.package.id,
    expectedTrainerId: client.trainerId,
    expectedSchedule: structuredClone(client.fixedWeeklySchedule),
    requestId: globalThis.crypto?.randomUUID?.() ?? `package-${Date.now()}-${Math.random().toString(36).slice(2)}`,
  }
}

export function buildPackageRenewal(db, client, draft, id) {
  requireActiveClient(client)
  for (const step of ['package', 'availability', 'matching']) {
    const errors = clientStepErrors({ ...draft, minimumStartDate: undefined }, step)
    if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
  }
  const trainer = db.trainers.find(item => item.id === draft.trainerId && item.status === 'active')
  if (!trainer) throw new Error('Choose an active trainer.')
  if (!GENDER_PREFERENCES.includes(draft.genderPreference)) throw new Error('Choose a trainer preference.')
  if ((draft.genderPreference === 'Female trainer preferred' && trainer.gender !== 'Female') ||
      (draft.genderPreference === 'Male trainer preferred' && trainer.gender !== 'Male')) throw new Error('The selected trainer does not match this preference.')
  const lastDay = clientPackages(client).filter(item => item.status !== 'inactive').map(item => item.endDate).sort().at(-1)
  if (lastDay && draft.startDate <= lastDay) throw new Error(`The new package must start after ${lastDay}, the last day of the existing packages.`)
  const definition = selectedPackage(db, draft)
  const schedule = structuredClone(draft.fixedWeeklySchedule)
  const scheduleErrors = clientStepErrors({ ...draft, clientPreferences: schedule.map(slot => ({ days: [slot.day], from: slot.from, to: slot.to })) }, 'availability')
  if (Object.keys(scheduleErrors).length || schedule.length !== Number(draft.sessionsPerWeek) ||
      new Set(schedule.map(slot => slot.id)).size !== schedule.length || schedule.some(slot => !slot.id ||
        !trainerCoversBlock(trainer, slot.day, slot.from, slot.to) ||
        !draft.clientPreferences.some(block => block.days.includes(slot.day) && block.from <= slot.from && slot.to <= block.to))) {
    throw new Error('Review the fixed weekly schedule against the selected trainer and client availability.')
  }
  const purchasedPackage = { id, templateId: definition.id, templateVersion: definition.version, name: definition.name,
    trainerId: trainer.id, genderPreference: draft.genderPreference, fixedWeeklySchedule: structuredClone(schedule), clientPreferences: structuredClone(draft.clientPreferences),
    ...packageFor(draft.startDate, draft.sessionsPerWeek, definition, db.settings.freeGymMinimumFrequency) }
  const sessions = buildClientSessions({ ...client, trainerId: trainer.id, package: purchasedPackage, fixedWeeklySchedule: schedule })
  if (sessions.length !== purchasedPackage.total) throw new Error('Every session must fit within package validity. Choose another frequency or package.')
  for (const session of sessions) {
    if (db.sessions.some(other => !['completed', 'cancelled'].includes(other.status) &&
      !sessionIsInactive(db.clients.find(item => item.id === other.clientId), other) &&
      other.date === session.date && (other.clientId === client.id || other.trainerId === trainer.id) &&
      other.from < session.to && session.from < other.to)) throw new Error(`The new package conflicts with a session on ${session.date}. Review the start date, trainer or weekly schedule.`)
  }
  return { purchasedPackage, schedule, sessions }
}

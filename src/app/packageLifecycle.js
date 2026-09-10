import { businessClock } from './clock.js'
import { clientPackages } from './clientPackages.js'

export function deactivatePurchase(purchased, staff, at, reason) {
  if (purchased.status === 'inactive') return
  const by = { id: staff.id, name: staff.name }
  Object.assign(purchased, { status: 'inactive', deactivatedAt: at, deactivatedBy: by, deactivationReason: reason })
  purchased.statusHistory = [...(purchased.statusHistory ?? []), { status: 'inactive', reason, at, by }]
}

export function restoreClientPurchases(client, at, by) {
  for (const purchased of clientPackages(client)) {
    if (purchased.status !== 'inactive' || purchased.deactivationReason !== 'client' || at < purchased.deactivatedAt) continue
    purchased.status = 'active'
    purchased.statusHistory = [...(purchased.statusHistory ?? []), { status: 'active', reason: 'client_reactivated', at, by }]
    delete purchased.deactivationReason
    delete purchased.deactivatedAt
    delete purchased.deactivatedBy
  }
}

function applyPurchaseSettings(client, purchased) {
  if (purchased.trainerId) client.trainerId = purchased.trainerId
  for (const key of ['fixedWeeklySchedule', 'clientPreferences', 'genderPreference']) {
    if (purchased[key] !== undefined) client[key] = structuredClone(purchased[key])
  }
}

// Upgrade only identifiable prior mutations. Never infer ownership from a person's name.
export function normalizePackageLifecycle(db, client) {
  const today = businessClock(new Date(), db.settings.timeZone).date
  for (const purchased of clientPackages(client)) {
    if (!purchased.renewalRequest) continue
    let request
    try { request = JSON.parse(purchased.renewalRequest) } catch { continue }
    const previous = (client.packageHistory ?? []).find(item => item.id === request.expectedPackageId)
    if (!previous) continue
    previous.trainerId ??= request.expectedTrainerId
  }
  const current = client.package
  if (!current) return
  if (current.startDate > today && current.renewalRequest) {
    let request
    try { request = JSON.parse(current.renewalRequest) } catch { /* An unknown legacy request remains untouched. */ }
    const previous = (client.packageHistory ?? []).find(item => item.id === request?.expectedPackageId && item.status !== 'inactive' && item.startDate <= today && today <= item.endDate)
    if (previous) {
      previous.trainerId ??= request.expectedTrainerId
      previous.fixedWeeklySchedule ??= structuredClone(request.expectedSchedule)
      client.packageHistory = client.packageHistory.filter(item => item.id !== previous.id)
      client.additionalPackages = [...(client.additionalPackages ?? []), current]
      client.package = previous
      applyPurchaseSettings(client, previous)
    }
  }
  const deactivation = (db.messages ?? []).filter(message => message.clientId === client.id && message.kind === 'client_status' && message.id.startsWith('client-off-')).sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0]
  for (const purchased of clientPackages(client)) {
    if (purchased.status === 'inactive' && !purchased.deactivationReason && purchased.deactivatedAt &&
      (purchased.deactivatedAt === client.deactivatedAt || purchased.deactivatedAt === deactivation?.createdAt)) purchased.deactivationReason = 'client'
  }
  if (client.status === 'inactive') return
  const reactivation = (db.messages ?? []).filter(message => message.clientId === client.id && message.kind === 'client_status' && message.id.startsWith('client-on-')).sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0]
  if (reactivation) restoreClientPurchases(client, reactivation.createdAt, client.reactivatedBy ?? { id: null, name: 'Unknown staff' })
  const due = (client.additionalPackages ?? []).filter(item => item.status !== 'inactive' && item.startDate <= today).sort((a, b) => a.startDate.localeCompare(b.startDate))
  for (const purchased of due) {
    if (client.package.status !== 'inactive' && client.package.endDate >= purchased.startDate) continue
    client.packageHistory = [client.package, ...(client.packageHistory ?? [])]
    client.additionalPackages = client.additionalPackages.filter(item => item.id !== purchased.id)
    client.package = purchased
    applyPurchaseSettings(client, purchased)
  }
}

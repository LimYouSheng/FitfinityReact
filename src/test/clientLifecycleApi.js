import { directoryData } from './directory.js'
export function deactivationReview(patch = {}) {
  const client = directoryData().clients[0]
  return { id: client.id, version: client.version, name: client.name, trainerId: client.trainer_id,
    purchases: client.purchases.map(p => ({ id: p.id, version: p.version, status: p.status, name: p.name })), ...patch }
}
export function reactivationReview(patch = {}) {
  const client = directoryData().clients[0]
  return { id: client.id, version: client.version, name: client.name, expected: 'a'.repeat(64), purchaseIds: [client.purchases[0].id], packageError: null,
    rows: [{ id: '10000000-0000-4000-8000-000000000020', version: 1, purchaseId: client.purchases[0].id, trainerId: client.trainer_id, trainerName: 'API Trainer', scheduleState: 'booked', originalDate: '2026-09-07', date: '2026-09-07', startsAt: '10:00', endsAt: '11:00', locked: false, error: null }], ...patch }
}

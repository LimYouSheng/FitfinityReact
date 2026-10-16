import { directoryId } from './directory.js'
import { staff } from './api.js'
export function calendarData() {
  return { viewerId: staff.id, sessions: [{ readAccess: 'operations', id: directoryId(30), version: 1, clientId: directoryId(7), purchaseId: directoryId(4), trainerId: directoryId(1), scheduleState: 'booked', sessionNumber: 1, date: '2026-10-13', startsAt: '10:00', endsAt: '11:00', status: 'scheduled' }], clients: [{ id: directoryId(7), name: 'API Client', kind: 'individual', status: 'active' }], trainers: [{ id: directoryId(1), name: 'API Trainer', status: 'active' }], purchases: [{ id: directoryId(4), clientId: directoryId(7), trainerId: directoryId(1), name: 'Purchased Twelve', status: 'active', stage: 'current', total: 12, used: 0, validityDays: 90, startDate: '2026-09-01', endDate: '2026-11-29' }] }
}
export function sessionDetailData() {
  const calendar = calendarData()
  return { session: calendar.sessions[0], client: calendar.clients[0], trainer: calendar.trainers[0], purchase: calendar.purchases[0], exercisePlan: [{ id: directoryId(40), version: 1, name: 'Stored Squat', weight: '12 kg', reps: '8', rounds: '3', rest: '60s', notes: 'Stored instruction', videoAttached: false }], exerciseResults: [{ id: directoryId(41), planItemId: directoryId(40), name: 'Stored Squat', loadKg: 12.5, reps: 8, sets: 3 }], acknowledgementHistory: [], trainerComments: 'Stored outcome', clientSummary: 'Stored client summary', whatsappOpenedAt: null, whatsappOpenCount: 0 }
}

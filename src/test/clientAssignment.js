import { directoryId } from './directory.js'

export const assignmentReview = () => ({ id: directoryId(7), version: 2, name: 'API Client', expected: 'a'.repeat(64),
  current: { id: directoryId(1), name: 'Current Trainer' },
  purchases: [{ id: directoryId(9), version: 1, trainerId: directoryId(1), name: 'Purchased Twelve' }],
  sessions: [{ id: directoryId(30), version: 1, trainerId: directoryId(1), purchaseId: directoryId(9), scheduleState: 'booked', date: '2027-06-07', startsAt: '10:00', endsAt: '11:00' }],
  choices: [{ id: directoryId(31), version: 1, name: 'Replacement Trainer', error: null }], history: [] })

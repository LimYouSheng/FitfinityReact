import { directoryId } from './directory.js'

export const trainerDeactivationReview = () => ({ id: directoryId(1), version: 1, name: 'API Trainer', accountId: directoryId(20), accountVersion: 1, expected: 'a'.repeat(64),
  sessions: [{ id: directoryId(30), version: 1, clientId: directoryId(7), clientName: 'API Client', purchaseId: directoryId(4), trainerId: directoryId(1), scheduleState: 'booked', date: '2027-06-07', startsAt: '10:00', endsAt: '11:00',
    choices: [{ id: directoryId(31), version: 1, name: 'Replacement Trainer', error: null }] }],
})

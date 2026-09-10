import { signatureFixture } from './signature.js'

// Exercise both pagers under the real shared history provider, using a closed
// cycle so this journey does not depend on today's date or the demo timetable.
export function withNavigationHistory(db) {
  const source = db.sessions.find(session => session.status === 'completed')
  db.trainers = [db.trainers[0], ...Array.from({ length: 11 }, (_, index) => ({
    ...db.trainers[0], id: `nav-trainer-${index}`, name: `A Trainer ${String(index).padStart(2, '0')}`,
  }))]
  db.sessions = Array.from({ length: 22 }, (_, index) => ({
    ...source, id: `nav-session-${String(index).padStart(2, '0')}`, clientId: 'c1', trainerId: 't1',
    date: '2020-08-20', from: '18:00', to: '19:00', status: 'completed',
    acknowledgement: { method: 'signature', signerName: 'Amanda Lim', signature: structuredClone(signatureFixture), recordedAt: '2020-08-20T11:00:00Z' },
  }))
  delete db.remunerationApprovals
  return db
}

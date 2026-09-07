export function payFixture() {
  return { users: [{ id: 'owner', role: 'owner' }, { id: 'trainer', role: 'trainer', trainerId: 't1' }],
    trainers: [{ id: 't1', name: 'Marcus', rates: { peak: 80, offPeak: 55 } }, { id: 't2', name: 'Rachel', rates: { peak: 80, offPeak: 55 } }],
    clients: [{ id: 'c1', name: 'Amanda', type: 'Individual', trainerId: 't1' }], messages: [],
    sessions: [{ id: 'pay1', trainerId: 't1', clientId: 'c1', date: '2026-08-20', from: '18:00', to: '19:00', status: 'completed', outcome: { durationMinutes: 60 }, acknowledgement: { method: 'signature', signerName: 'Amanda', recordedAt: '2026-08-20T19:00:00+08:00' } }] }
}

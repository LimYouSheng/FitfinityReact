export const seed = {
  users: [
    { id: 'u-owner', name: 'Chau', role: 'owner' },
    { id: 'u-marcus', name: 'Marcus Tan', role: 'trainer', trainerId: 't1', profile: 'Fully supervised' },
    { id: 'u-aisha', name: 'Aisha Rahman', role: 'trainer', trainerId: 't2', profile: 'Partially autonomous' },
    { id: 'u-jason', name: 'Jason Lee', role: 'trainer', trainerId: 't3', profile: 'Fully autonomous' },
  ],
  trainers: [
    {
      id: 't1', name: 'Marcus Tan', email: 'marcus@fitfinity.sg', phone: '+65 9888 1122', specialty: 'Strength & conditioning',
      approvalNeeded: { availability: true, sessionTime: true, trainerReassignment: true, fixedWeeklySchedule: true },
    },
    {
      id: 't2', name: 'Aisha Rahman', email: 'aisha@fitfinity.sg', phone: '+65 9777 2255', specialty: 'General fitness',
      approvalNeeded: { availability: true, sessionTime: false, trainerReassignment: true, fixedWeeklySchedule: false },
    },
    {
      id: 't3', name: 'Jason Lee', email: 'jason@fitfinity.sg', phone: '+65 9666 3388', specialty: 'Mobility & conditioning',
      approvalNeeded: { availability: false, sessionTime: false, trainerReassignment: false, fixedWeeklySchedule: false },
    },
  ],
  clients: [
    {
      id: 'c1', type: 'Individual', name: 'Amanda Lim', phone: '+65 9123 4567', email: 'amanda@example.com', birthday: '1994-04-12', gender: 'Female',
      emergencyContact: 'Jason Lim • +65 9000 1122', startDate: '2026-08-18', trainerId: 't1', trainerPreference: 'No gender preference',
      healthNotes: 'Previous right-knee discomfort. Check current symptoms before lower-body loading. Avoid sudden high-impact volume increases.',
      remarks: 'Prefers evening sessions. Keep progression gradual and review goals at renewal.',
      fixedWeeklySchedule: [
        { id: 'slot1', day: 'Monday', from: '18:00', to: '19:00' },
        { id: 'slot2', day: 'Wednesday', from: '18:00', to: '19:00' },
      ],
      package: { total: 12, used: 3, startDate: '2026-08-15', validityDays: 90, endDate: '2026-09-22' },
      lastTrained: '2026-08-29', renewal: '9 sessions remaining',
    },
    {
      id: 'c2', type: 'Couple', name: 'Daniel & Mei Wong', phone: '+65 9234 8899', email: 'wong@example.com', birthday: '1990-03-04', gender: 'Couple',
      emergencyContact: 'Family contact • +65 9001 2200', startDate: '2026-08-05', trainerId: 't2', trainerPreference: 'No gender preference',
      healthNotes: 'Daniel: shoulder history. Mei: no current limitations.', remarks: 'Weekend sessions preferred.',
      fixedWeeklySchedule: [{ id: 'slot3', day: 'Saturday', from: '10:00', to: '11:00' }],
      package: { total: 24, used: 7, startDate: '2026-08-05', validityDays: 180, endDate: '2027-02-01' },
      lastTrained: '2026-08-28', renewal: '17 sessions remaining',
    },
    {
      id: 'c3', type: 'Individual', name: 'Nadia Koh', phone: '+65 9345 7788', email: 'nadia@example.com', birthday: '1988-11-19', gender: 'Female',
      emergencyContact: 'Eric Koh • +65 9012 7788', startDate: '2026-07-22', trainerId: 't3', trainerPreference: 'Female trainer preferred',
      healthNotes: 'No current limitations.', remarks: 'Early weekday sessions.',
      fixedWeeklySchedule: [{ id: 'slot4', day: 'Tuesday', from: '07:00', to: '08:00' }],
      package: { total: 12, used: 10, startDate: '2026-07-22', validityDays: 90, endDate: '2026-10-19' },
      lastTrained: '2026-08-30', renewal: 'Renewal follow-up',
    },
  ],
}

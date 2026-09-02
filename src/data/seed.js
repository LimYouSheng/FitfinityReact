const availability = {
  marcus: {
    Monday: [['18:00','21:00']], Tuesday: [['18:00','21:00']], Wednesday: [['18:00','21:00']],
    Thursday: [['18:00','21:00']], Friday: [['18:00','20:00']], Saturday: [['09:00','13:00']], Sunday: [],
  },
  rachel: {
    Monday: [['18:00','21:00']], Tuesday: [['18:00','21:00']], Wednesday: [['18:00','21:00']],
    Thursday: [['19:00','21:00']], Friday: [['18:00','21:00']], Saturday: [['09:00','12:00']], Sunday: [],
  },
  daniel: {
    Monday: [['17:00','20:00']], Tuesday: [['18:00','20:00']], Wednesday: [['17:00','20:00']],
    Thursday: [['18:00','20:00']], Friday: [['17:00','19:00']], Saturday: [['08:00','12:00']], Sunday: [],
  },
  priya: {
    Monday: [['08:00','12:00']], Tuesday: [['18:00','21:00']], Wednesday: [['08:00','12:00']],
    Thursday: [['18:00','21:00']], Friday: [['08:00','12:00']], Saturday: [['09:00','13:00']], Sunday: [],
  },
  jerome: {
    Monday: [['18:00','21:00']], Tuesday: [['18:00','21:00']], Wednesday: [['18:00','21:00']],
    Thursday: [['18:00','21:00']], Friday: [['18:00','20:00']], Saturday: [['10:00','14:00']], Sunday: [],
  },
  aisha: {
    Monday: [['09:00','13:00']], Tuesday: [['18:00','21:00']], Wednesday: [['09:00','13:00']],
    Thursday: [['18:00','21:00']], Friday: [['09:00','13:00']], Saturday: [['09:00','12:00']], Sunday: [],
  },
  kelvin: {
    Monday: [['18:00','20:00']], Tuesday: [['18:00','20:00']], Wednesday: [['18:00','20:00']],
    Thursday: [['18:00','20:00']], Friday: [['18:00','20:00']], Saturday: [['08:00','11:00']], Sunday: [],
  },
}

export const seed = {
  users: [
    { id: 'u-owner', name: 'Chau', role: 'owner', status: 'active' },
    { id: 'u-marcus', name: 'Marcus Tan', role: 'trainer', trainerId: 't1', profile: 'Fully supervised', status: 'active' },
    { id: 'u-aisha', name: 'Aisha Rahman', role: 'trainer', trainerId: 't6', profile: 'Partially autonomous', status: 'active' },
    { id: 'u-daniel', name: 'Daniel Lee', role: 'trainer', trainerId: 't3', profile: 'Fully autonomous', status: 'active' },
  ],

  trainers: [
    {
      id: 't1', status: 'active', name: 'Marcus Tan', phone: '+65 9888 1122', email: 'marcus@fitfinity.sg',
      birthday: '1991-06-14', gender: 'Male', trainerType: 'Strength & Conditioning',
      qualifications: 'NSCA-CPT, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.marcus,
      monthlyActivity: { sessions: 62, hours: 62, peak: 40, offPeak: 22 },
      approvalNeeded: { availability: true, sessionTime: true, trainerReassignment: true, fixedWeeklySchedule: true },
    },
    {
      id: 't2', status: 'active', name: 'Rachel Ong', phone: '+65 9771 2233', email: 'rachel@fitfinity.sg',
      birthday: '1993-02-08', gender: 'Female', trainerType: 'Strength & Functional Training',
      qualifications: 'ACE-CPT, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.rachel,
      monthlyActivity: { sessions: 56, hours: 56, peak: 36, offPeak: 20 },
      approvalNeeded: { availability: true, sessionTime: true, trainerReassignment: true, fixedWeeklySchedule: true },
    },
    {
      id: 't3', status: 'active', name: 'Daniel Lee', phone: '+65 9662 4488', email: 'daniel@fitfinity.sg',
      birthday: '1989-10-21', gender: 'Male', trainerType: 'Performance & Conditioning',
      qualifications: 'NASM-CPT, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.daniel,
      monthlyActivity: { sessions: 48, hours: 48, peak: 30, offPeak: 18 },
      approvalNeeded: { availability: false, sessionTime: false, trainerReassignment: false, fixedWeeklySchedule: false },
    },
    {
      id: 't4', status: 'active', name: 'Priya Nair', phone: '+65 9553 7721', email: 'priya@fitfinity.sg',
      birthday: '1992-04-17', gender: 'Female', trainerType: 'Strength & Mobility',
      qualifications: 'ACE-CPT, Mobility Specialist, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.priya,
      monthlyActivity: { sessions: 46, hours: 46, peak: 29, offPeak: 17 },
      approvalNeeded: { availability: true, sessionTime: false, trainerReassignment: true, fixedWeeklySchedule: false },
    },
    {
      id: 't5', status: 'active', name: 'Jerome Goh', phone: '+65 9442 1189', email: 'jerome@fitfinity.sg',
      birthday: '1988-12-02', gender: 'Male', trainerType: 'Fat Loss & Conditioning',
      qualifications: 'ISSA-CPT, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.jerome,
      monthlyActivity: { sessions: 39, hours: 39, peak: 24, offPeak: 15 },
      approvalNeeded: { availability: true, sessionTime: true, trainerReassignment: false, fixedWeeklySchedule: true },
    },
    {
      id: 't6', status: 'active', name: 'Aisha Rahman', phone: '+65 9331 5560', email: 'aisha@fitfinity.sg',
      birthday: '1994-08-29', gender: 'Female', trainerType: 'Mobility & General Fitness',
      qualifications: 'ACE-CPT, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.aisha,
      monthlyActivity: { sessions: 36, hours: 36, peak: 22, offPeak: 14 },
      approvalNeeded: { availability: true, sessionTime: false, trainerReassignment: true, fixedWeeklySchedule: false },
    },
    {
      id: 't7', status: 'active', name: 'Kelvin Chua', phone: '+65 9228 4480', email: 'kelvin@fitfinity.sg',
      birthday: '1990-01-11', gender: 'Male', trainerType: 'Strength',
      qualifications: 'CPT, CPR/AED', publicProfile: 'Hidden',
      rates: { peak: 80, offPeak: 55 }, availability: availability.kelvin,
      monthlyActivity: { sessions: 31, hours: 31, peak: 19, offPeak: 12 },
      approvalNeeded: { availability: true, sessionTime: true, trainerReassignment: true, fixedWeeklySchedule: true },
    },
  ],

  clients: [
    {
      id: 'c1', status: 'active', type: 'Individual', name: 'Amanda Lim',
      phone: '+65 9123 4567', email: 'amanda@example.com', birthday: '1994-04-12', gender: 'Female',
      emergencyContact: 'Jason Lim • +65 9000 1122', startDate: '2026-08-18', trainerId: 't1',
      trainerPreference: 'No gender preference',
      healthNotes: 'Previous right-knee discomfort. Check current symptoms before lower-body loading. Avoid sudden high-impact volume increases.',
      remarks: 'Prefers evening sessions. Keep progression gradual and review goals at renewal.',
      fixedWeeklySchedule: [
        { id: 'slot1', day: 'Monday', from: '18:00', to: '19:00' },
        { id: 'slot2', day: 'Wednesday', from: '18:00', to: '19:00' },
      ],
      package: { total: 12, used: 3, startDate: '2026-08-15', validityDays: 90, endDate: '2026-11-12' },
      lastTrained: '2026-08-29', renewal: '9 sessions remaining',
    },
    {
      id: 'c2', status: 'active', type: 'Couple', name: 'Daniel & Mei Wong',
      phone: '+65 9234 8899', email: 'wong@example.com', birthday: '1990-03-04', gender: 'Couple',
      emergencyContact: 'Family contact • +65 9001 2200', startDate: '2026-08-05', trainerId: 't6',
      trainerPreference: 'No gender preference',
      healthNotes: 'Daniel: shoulder history. Mei: no current limitations.',
      remarks: 'Weekend sessions preferred.',
      fixedWeeklySchedule: [{ id: 'slot3', day: 'Saturday', from: '10:00', to: '11:00' }],
      package: { total: 24, used: 7, startDate: '2026-08-05', validityDays: 180, endDate: '2027-02-01' },
      lastTrained: '2026-08-28', renewal: '17 sessions remaining',
    },
    {
      id: 'c3', status: 'active', type: 'Individual', name: 'Nadia Koh',
      phone: '+65 9345 7788', email: 'nadia@example.com', birthday: '1988-11-19', gender: 'Female',
      emergencyContact: 'Eric Koh • +65 9012 7788', startDate: '2026-07-22', trainerId: 't4',
      trainerPreference: 'Female trainer preferred',
      healthNotes: 'No current limitations.', remarks: 'Early weekday sessions.',
      fixedWeeklySchedule: [{ id: 'slot4', day: 'Tuesday', from: '08:00', to: '09:00' }],
      package: { total: 12, used: 10, startDate: '2026-07-22', validityDays: 90, endDate: '2026-10-19' },
      lastTrained: '2026-08-30', renewal: 'Renewal follow-up',
    },
    {
      id: 'c4', status: 'active', type: 'Individual', name: 'Farah Noor',
      phone: '+65 9455 3301', email: 'farah@example.com', birthday: '1996-05-20', gender: 'Female',
      emergencyContact: 'Family • +65 9008 1110', startDate: '2026-08-01', trainerId: 't2',
      trainerPreference: 'Female trainer preferred',
      healthNotes: 'No current limitations.', remarks: 'Saturday mornings preferred.',
      fixedWeeklySchedule: [{ id: 'slot5', day: 'Saturday', from: '09:00', to: '10:00' }],
      package: { total: 12, used: 4, startDate: '2026-08-01', validityDays: 90, endDate: '2026-10-29' },
      lastTrained: '2026-08-29', renewal: '8 sessions remaining',
    },
  ],

  sessions: [
    { id: 's1', clientId: 'c1', trainerId: 't1', date: '2026-09-02', from: '18:00', to: '19:00', status: 'planned' },
    { id: 's2', clientId: 'c1', trainerId: 't1', date: '2026-09-07', from: '18:00', to: '19:00', status: 'not_planned' },
    { id: 's3', clientId: 'c2', trainerId: 't6', date: '2026-09-05', from: '10:00', to: '11:00', status: 'planned' },
    { id: 's4', clientId: 'c4', trainerId: 't2', date: '2026-09-05', from: '09:00', to: '10:00', status: 'planned' },
  ],

  messages: [
    {
      id: 'm1', createdAt: '2026-09-01T09:00:00+08:00', recipientRole: 'owner',
      title: 'Messages foundation ready',
      body: 'Requests and operational updates now share one Messages destination. Request workflows will plug into this feed as each domain is migrated.',
      kind: 'system', read: false,
    },
    {
      id: 'm2', createdAt: '2026-09-01T09:10:00+08:00', recipientTrainerId: 't1',
      title: 'Trainer messages ready',
      body: 'Approvals, assignments and client-status updates will appear here.',
      kind: 'system', read: false,
    },
    {
      id: 'm3', createdAt: '2026-09-01T10:00:00+08:00', recipientRole: 'owner',
      title: 'Renewal follow-up: Nadia Koh',
      body: 'Nadia Koh is approaching package renewal. Review remaining sessions and follow up when appropriate.',
      kind: 'renewal', read: false,
    },
  ],
}

import { mockPolicy } from './mockPolicy.js'
import { DEFAULT_EXERCISES } from './mockExercises.js'
import { DEFAULT_PACKAGES } from './mockPackages.js'
import { appendRenewalMessage } from '../app/renewals.js'

const availability = {
  marcus: {
    Monday: [['18:00', '21:00']], Tuesday: [['18:00', '21:00']], Wednesday: [['18:00', '21:00']],
    Thursday: [['18:00', '21:00']], Friday: [['18:00', '20:00']], Saturday: [['09:00', '13:00']], Sunday: [],
  },
  rachel: {
    Monday: [['18:00', '21:00']], Tuesday: [['18:00', '21:00']], Wednesday: [['18:00', '21:00']],
    Thursday: [['19:00', '21:00']], Friday: [['18:00', '21:00']], Saturday: [['09:00', '12:00']], Sunday: [],
  },
  daniel: {
    Monday: [['17:00', '20:00']], Tuesday: [['18:00', '20:00']], Wednesday: [['17:00', '20:00']],
    Thursday: [['18:00', '20:00']], Friday: [['17:00', '19:00']], Saturday: [['08:00', '12:00']], Sunday: [],
  },
  priya: {
    Monday: [['08:00', '12:00']], Tuesday: [['18:00', '21:00']], Wednesday: [['08:00', '12:00']],
    Thursday: [['18:00', '21:00']], Friday: [['08:00', '12:00']], Saturday: [['09:00', '13:00']], Sunday: [],
  },
  jerome: {
    Monday: [['18:00', '21:00']], Tuesday: [['18:00', '21:00']], Wednesday: [['18:00', '21:00']],
    Thursday: [['18:00', '21:00']], Friday: [['18:00', '20:00']], Saturday: [['10:00', '14:00']], Sunday: [],
  },
  aisha: {
    Monday: [['09:00', '13:00']], Tuesday: [['18:00', '21:00']], Wednesday: [['09:00', '13:00']],
    Thursday: [['18:00', '21:00']], Friday: [['09:00', '13:00']], Saturday: [['09:00', '12:00']], Sunday: [],
  },
  kelvin: {
    Monday: [['18:00', '20:00']], Tuesday: [['18:00', '20:00']], Wednesday: [['18:00', '20:00']],
    Thursday: [['18:00', '20:00']], Friday: [['18:00', '20:00']], Saturday: [['08:00', '11:00']], Sunday: [],
  },
}

const approvals = {
  availability: true,
  sessionTime: true,
  trainerReassignment: true,
  fixedWeeklySchedule: true,
}

const additionalTrainerSpecs = [
  ['t8', 'Sofia Chen', 'Female', 'Mobility & Rehabilitation', 'ACE-CPT, FRC Mobility Specialist', 'priya', 44],
  ['t9', 'Ethan Ng', 'Male', 'Strength & Conditioning', 'NSCA-CPT, CPR/AED', 'daniel', 42],
  ['t10', 'Melissa Teo', 'Female', 'Pre/Post-Natal Fitness', 'ACE-CPT, Pre/Post-Natal Specialist', 'aisha', 37],
  ['t11', 'Ryan Ho', 'Male', 'Functional Fitness', 'NASM-CPT, CPR/AED', 'jerome', 35],
  ['t12', 'Nur Izzati', 'Female', 'General Fitness & Mobility', 'ACE-CPT, CPR/AED', 'rachel', 33],
]

const additionalTrainers = additionalTrainerSpecs.map(([
  id,
  name,
  gender,
  trainerType,
  qualifications,
  availabilityKey,
  monthlySessions,
], index) => ({
  id,
  status: 'active',
  name,
  phone: `+65 91${40 + index} ${2200 + index * 113}`,
  email: `${name.toLowerCase().replaceAll(' ', '.')}@fitfinity.sg`,
  birthday: `199${index + 1}-0${(index % 8) + 1}-${10 + index}`,
  gender,
  trainerType,
  qualifications,
  publicProfile: 'Visible',
  rates: { peak: 80, offPeak: 55 },
  availability: availability[availabilityKey],
  monthlyActivity: {
    sessions: monthlySessions,
    hours: monthlySessions,
    peak: Math.round(monthlySessions * 0.62),
    offPeak: monthlySessions - Math.round(monthlySessions * 0.62),
  },
  approvalNeeded: { ...approvals },
}))

const packageHistoryFor = (clientId, total, index) => [
  {
    id: `${clientId}-package-2026-1`,
    total,
    used: total,
    startDate: `2026-0${index % 3 + 2}-01`,
    endDate: `2026-0${index % 3 + 5}-01`,
  },
  {
    id: `${clientId}-package-2025-2`,
    total: 12,
    used: 12,
    startDate: '2025-10-01',
    endDate: '2026-01-15',
  },
]

const oracleStrengthProgress = [
  {
    name: 'Smith back squat', sets: 3, reps: 8,
    points: [['2026-07-10', 12.5], ['2026-07-18', 15], ['2026-07-28', 17.5], ['2026-08-04', 20], ['2026-08-17', 22.5], ['2026-08-21', 25]],
  },
  {
    name: 'Leg press', sets: 3, reps: 10,
    points: [['2026-07-08', 50], ['2026-07-20', 55], ['2026-07-30', 60], ['2026-08-07', 66], ['2026-08-19', 72]],
  },
  {
    name: 'Smith chest press', sets: 3, reps: 10,
    points: [['2026-07-12', 10], ['2026-07-24', 12.5], ['2026-08-04', 12.5], ['2026-08-14', 15], ['2026-08-17', 15]],
  },
  {
    name: 'Seated row', sets: 3, reps: 10,
    points: [['2026-07-09', 14], ['2026-07-21', 16], ['2026-08-02', 18], ['2026-08-11', 18], ['2026-08-17', 20]],
  },
  {
    name: 'DB shoulder press (incline bench and flat bench)', shortName: 'DB shoulder press', sets: 3, reps: 8,
    points: [['2026-07-15', 6], ['2026-07-27', 7.5], ['2026-08-04', 7.5], ['2026-08-14', 8], ['2026-08-21', 10]],
  },
  {
    name: 'Smith deadlift', sets: 3, reps: 8,
    points: [['2026-07-11', 15], ['2026-07-23', 17.5], ['2026-08-07', 17.5], ['2026-08-11', 20], ['2026-08-21', 20]],
  },
]

const strengthProgressFor = clientId => oracleStrengthProgress.map((exercise, exerciseIndex) => ({
  ...exercise,
  id: `${clientId}-strength-${exerciseIndex + 1}`,
  points: exercise.points.map(([date, load], pointIndex) => ({
    id: `${clientId}-strength-${exerciseIndex + 1}-${pointIndex + 1}`,
    date,
    load,
  })),
}))

const baseClients = [
  {
    id: 'c1', status: 'active', type: 'Individual', name: 'Amanda Lim',
    phone: { countryCode: '+65', number: '9123 4567' }, email: 'amanda@example.com', birthday: '1994-04-12', gender: 'Female',
    emergencyContact: { name: 'Jason Lim', relationship: 'Spouse', countryCode: '+65', number: '9000 1122' }, startDate: '2026-08-18', trainerId: 't1',
    genderPreference: 'No gender preference',
    healthNotes: 'Previous right-knee discomfort. Check current symptoms before lower-body loading. Avoid sudden high-impact volume increases.',
    remarks: 'Prefers evening sessions. Keep progression gradual and review goals at renewal.',
    fixedWeeklySchedule: [
      { id: 'slot1', day: 'Monday', from: '18:00', to: '19:00' },
    ],
    package: { durationWeeks: 12, sessionsPerWeek: 1, total: 12, used: 3, startDate: '2026-08-15', validityDays: 90, endDate: '2026-11-12' },
    packageHistory: packageHistoryFor('c1', 12, 1), strengthProgress: strengthProgressFor('c1'),
    lastTrained: '2026-08-29',
  },
  {
    id: 'c2', status: 'active', type: 'Couple', name: 'Daniel & Mei Wong',
    phone: { countryCode: '+65', number: '9234 8899' }, email: 'wong@example.com', birthday: '1990-03-04', gender: 'Couple',
    emergencyContact: { name: 'Mei Wong', relationship: 'Partner', countryCode: '+65', number: '9001 2200' }, startDate: '2026-08-05', trainerId: 't6',
    genderPreference: 'No gender preference', healthNotes: 'Daniel: shoulder history. Mei: no current limitations.',
    remarks: 'Weekend sessions preferred.',
    fixedWeeklySchedule: [{ id: 'slot3', day: 'Wednesday', from: '19:00', to: '20:00' }, { id: 'slot3b', day: 'Saturday', from: '10:00', to: '11:00' }],
    package: { durationWeeks: 12, sessionsPerWeek: 2, total: 24, used: 7, startDate: '2026-08-05', validityDays: 90, endDate: '2026-11-02' },
    packageHistory: packageHistoryFor('c2', 24, 2), strengthProgress: strengthProgressFor('c2'),
    lastTrained: '2026-08-28',
  },
  {
    id: 'c3', status: 'active', type: 'Individual', name: 'Nadia Koh',
    phone: { countryCode: '+65', number: '9345 7788' }, email: 'nadia@example.com', birthday: '1988-11-19', gender: 'Female',
    emergencyContact: { name: 'Eric Koh', relationship: 'Sibling', countryCode: '+65', number: '9012 7788' }, startDate: '2026-07-22', trainerId: 't4',
    genderPreference: 'Female trainer preferred', healthNotes: 'No current limitations.', remarks: 'Early weekday sessions.',
    fixedWeeklySchedule: [{ id: 'slot4', day: 'Tuesday', from: '08:00', to: '09:00' }],
    package: { durationWeeks: 12, sessionsPerWeek: 1, total: 12, used: 10, startDate: '2026-07-22', validityDays: 90, endDate: '2026-10-19' },
    packageHistory: packageHistoryFor('c3', 12, 3), strengthProgress: strengthProgressFor('c3'),
    lastTrained: '2026-08-30',
  },
  {
    id: 'c4', status: 'active', type: 'Individual', name: 'Farah Noor',
    phone: { countryCode: '+65', number: '9455 3301' }, email: 'farah@example.com', birthday: '1996-05-20', gender: 'Female',
    emergencyContact: { name: 'Noor Aziz', relationship: 'Parent', countryCode: '+65', number: '9008 1110' }, startDate: '2026-08-01', trainerId: 't2',
    genderPreference: 'Female trainer preferred', healthNotes: 'No current limitations.', remarks: 'Saturday mornings preferred.',
    fixedWeeklySchedule: [{ id: 'slot5', day: 'Saturday', from: '09:00', to: '10:00' }],
    package: { durationWeeks: 12, sessionsPerWeek: 1, total: 12, used: 4, startDate: '2026-08-01', validityDays: 90, endDate: '2026-10-29' },
    packageHistory: packageHistoryFor('c4', 12, 4), strengthProgress: strengthProgressFor('c4'),
    lastTrained: '2026-08-29',
  },
]

const additionalClientSpecs = [
  ['Benjamin Tan', 'Male', 'Individual', 't3'],
  ['Cheryl Goh', 'Female', 'Individual', 't5'],
  ['Ethan & Grace Lee', 'Couple', 'Couple', 't7'],
  ['Hafiz Rahman', 'Male', 'Individual', 't8'],
  ['Joanne Tay', 'Female', 'Individual', 't9'],
  ['Kevin Low', 'Male', 'Individual', 't10'],
  ['Lina Chua', 'Female', 'Individual', 't11'],
  ['Michael Sim', 'Male', 'Individual', 't12'],
  ['Olivia Neo', 'Female', 'Individual', 't3'],
  ['Pravin Kumar', 'Male', 'Individual', 't5'],
  ['Sarah Yeo', 'Female', 'Individual', 't8'],
  ['Thomas Ang', 'Male', 'Individual', 't9'],
]

const additionalClients = additionalClientSpecs.map(([name, gender, type, trainerId], index) => {
  const id = `c${index + 5}`
  const total = type === 'Couple' || index % 4 === 0 ? 24 : 12
  const sessionsPerWeek = total === 24 ? 2 : 1
  const used = total === 24 ? 8 + (index % 2) : 4 + (index % 6)
  const startDay = String(3 + index).padStart(2, '0')
  return {
    id,
    status: index === 10 ? 'inactive' : 'active',
    type,
    name,
    phone: { countryCode: '+65', number: `9${310 + index} ${4100 + index * 127}` },
    email: `${name.toLowerCase().replaceAll(' & ', '.').replaceAll(' ', '.')}@example.com`,
    birthday: `199${index % 7}-0${index % 8 + 1}-${String(9 + index).padStart(2, '0')}`,
    gender,
    emergencyContact: { name: `Emergency Contact ${index + 1}`, relationship: index % 2 ? 'Sibling' : 'Parent', countryCode: '+65', number: `8${700 + index} ${2100 + index * 91}` },
    startDate: `2026-06-${startDay}`,
    trainerId,
    genderPreference: index % 3 === 0 ? 'Female trainer preferred' : 'No gender preference',
    healthNotes: index % 4 === 0 ? 'Monitor lower-back comfort during loaded hinging.' : 'No current limitations.',
    remarks: index % 2 === 0 ? 'Prefers weekday evening sessions.' : 'Prefers weekend morning sessions.',
    fixedWeeklySchedule: [{
      id: `${id}-slot-1`, day: index % 2 === 0 ? 'Wednesday' : 'Saturday',
      from: index % 2 === 0 ? '19:00' : '10:00', to: index % 2 === 0 ? '20:00' : '11:00',
    }, ...(sessionsPerWeek === 2 ? [{ id: `${id}-slot-2`, day: 'Sunday', from: '10:00', to: '11:00' }] : [])],
    package: { durationWeeks: 12, sessionsPerWeek, total, used, startDate: '2026-08-01', validityDays: 90, endDate: '2026-10-29' },
    packageHistory: packageHistoryFor(id, total, index + 5),
    strengthProgress: strengthProgressFor(id),
    lastTrained: `2026-08-${String(18 + (index % 12)).padStart(2, '0')}`,
  }
})

const allClients = [...baseClients, ...additionalClients].map(client => ({
  ...client, package: { ...client.package, id: `client-package-${client.id}` },
}))

const exerciseTemplates = [
  ['Goblet Squat', '16 kg', '10', '3', '60 sec'],
  ['Seated Cable Row', '24 kg', '12', '3', '60 sec'],
  ['DB Chest Press', '10 kg', '10', '3', '75 sec'],
  ['Romanian Deadlift', '30 kg', '8', '4', '90 sec'],
  ['Lat Pulldown', '28 kg', '12', '3', '60 sec'],
  ['Walking Lunge', '8 kg', '10 / side', '3', '60 sec'],
]

const plannedExercises = (sessionId, offset = 0) => [0, 1].map((step) => {
  const [name, weight, reps, rounds, rest] = exerciseTemplates[(offset + step) % exerciseTemplates.length]
  return {
    id: `${sessionId}-exercise-${step + 1}`,
    name,
    weight,
    reps,
    rounds,
    rest,
    customDetails: step === 0 ? [{ id: `${sessionId}-detail-1`, value: 'Controlled tempo' }] : [],
    videoAttached: step === 1,
  }
})

const completedSessionCounts = Object.fromEntries(allClients.map(client => [client.id, client.package.used]))
completedSessionCounts.c1 = 2

const generatedCompletedSessions = allClients.flatMap((client, clientIndex) =>
  Array.from({ length: completedSessionCounts[client.id] }, (_, sessionIndex) => {
    const id = `history-${client.id}-${sessionIndex + 1}`
    const day = String(2 + ((clientIndex * 3 + sessionIndex * 2) % 27)).padStart(2, '0')
    const from = clientIndex % 2 === 0 ? '18:00' : '10:00'
    const to = clientIndex % 2 === 0 ? '19:00' : '11:00'
    return {
      id,
      clientId: client.id,
      trainerId: client.trainerId,
      date: `2026-08-${day}`,
      from,
      to,
      sessionNumber: sessionIndex + 1,
      packageTotal: client.package.total,
      status: 'completed',
      exercisePlan: plannedExercises(id, clientIndex + sessionIndex),
      outcome: { durationMinutes: 60, trainerComments: 'Completed as planned with consistent technique.' },
      acknowledgement: {
        method: 'signature', signerName: client.name, note: '',
        recordedAt: `2026-08-${day}T${to}:00+08:00`,
      },
      whatsappOpenedAt: `2026-08-${day}T${to}:05+08:00`,
    }
  }),
)

const featuredUpcomingNumbers = {
  c1: new Set([4, 5]),
  c2: new Set([8]),
  c3: new Set([11, 12]),
  c4: new Set([5]),
}

const addDays = (date, days) => {
  const value = new Date(`${date}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() + days)
  return value.toISOString().slice(0, 10)
}

const generatedUpcomingSessions = allClients
  .filter(client => client.status !== 'inactive')
  .flatMap((client, clientIndex) => {
    const firstSessionNumber = client.package.used + 1
    const frequency = client.package.sessionsPerWeek

    return Array.from(
      { length: client.package.total - client.package.used },
      (_, sessionIndex) => firstSessionNumber + sessionIndex,
    )
      .filter(sessionNumber => !featuredUpcomingNumbers[client.id]?.has(sessionNumber))
      .map(sessionNumber => {
        const sequence = sessionNumber - firstSessionNumber
        const id = `upcoming-${client.id}-${sessionNumber}`
        const planned = sequence < 2
        const from = clientIndex % 2 === 0 ? '19:00' : '10:00'
        const to = clientIndex % 2 === 0 ? '20:00' : '11:00'
        const interval = frequency === 2 ? 3.5 : 7

        return {
          id,
          clientId: client.id,
          trainerId: client.trainerId,
          date: addDays('2026-09-03', Math.floor(sequence * interval) + (clientIndex % 3)),
          from,
          to,
          sessionNumber,
          packageTotal: client.package.total,
          status: planned ? 'planned' : 'not_planned',
          exercisePlan: planned ? plannedExercises(id, clientIndex + sequence) : [],
        }
      })
  })

const featuredSessions = [
  {
    id: 's0', clientId: 'c1', trainerId: 't1', date: '2026-08-29', from: '18:00', to: '19:00',
    sessionNumber: 3, packageTotal: 12, status: 'completed', exercisePlan: plannedExercises('s0'),
    outcome: { durationMinutes: 60, trainerComments: 'Load progressed with consistent technique.' },
    acknowledgement: { method: 'signature', signerName: 'Amanda Lim', note: '', recordedAt: '2026-08-29T19:03:00+08:00' },
    whatsappOpenedAt: '2026-08-29T19:08:00+08:00',
  },
  {
    id: 's1', clientId: 'c1', trainerId: 't1', date: '2026-09-02', from: '18:00', to: '19:00',
    sessionNumber: 4, packageTotal: 12, status: 'planned', exercisePlan: plannedExercises('s1', 2),
    outcome: { durationMinutes: 60, trainerComments: 'Load progressed with consistent technique.' },
  },
  { id: 's2', clientId: 'c1', trainerId: 't1', date: '2026-09-07', from: '18:00', to: '19:00', sessionNumber: 5, packageTotal: 12, status: 'not_planned', exercisePlan: [] },
  { id: 's3', clientId: 'c2', trainerId: 't6', date: '2026-09-05', from: '10:00', to: '11:00', sessionNumber: 8, packageTotal: 24, status: 'planned', exercisePlan: plannedExercises('s3', 1) },
  { id: 's4', clientId: 'c4', trainerId: 't2', date: '2026-09-05', from: '09:00', to: '10:00', sessionNumber: 5, packageTotal: 12, status: 'planned', exercisePlan: plannedExercises('s4', 3) },
  { id: 's5', clientId: 'c3', trainerId: 't4', date: '2026-09-08', from: '08:00', to: '09:00', sessionNumber: 11, packageTotal: 12, status: 'planned', exercisePlan: plannedExercises('s5', 4) },
  { id: 's6', clientId: 'c3', trainerId: 't4', date: '2026-09-15', from: '08:00', to: '09:00', sessionNumber: 12, packageTotal: 12, status: 'not_planned', exercisePlan: [] },
]

const generatedCreditTransactions = generatedCompletedSessions.map(session => ({
  id: `credit-${session.id}`,
  type: 'session_debit',
  sessionId: session.id,
  clientId: session.clientId,
  amount: -1,
  createdAt: `${session.date}T${session.to}:00+08:00`,
}))

const generatedMessages = allClients.slice(0, 12).map((client, index) => ({
  id: `demo-message-${index + 1}`,
  createdAt: `2026-09-0${(index % 2) + 1}T${String(10 + (index % 9)).padStart(2, '0')}:15:00+08:00`,
  recipientRole: 'owner',
  clientId: client.id,
  trainerId: client.trainerId,
  title: `Session update: ${client.name}`,
  body: `${client.name}'s latest session record is ready for review.`,
  kind: 'session',
  read: index > 4,
}))

const initialRenewals = { settings: mockPolicy, messages: [] }
for (const client of allClients) {
  const message = appendRenewalMessage(initialRenewals, client, '2026-09-02T21:00:00+08:00')
  // Preserve the original demo record's identity for saved read state and routes.
  if (message && client.id === 'c3') message.id = 'm3'
}

export const seed = {
  renewalMessageVersion: 1,
  settings: structuredClone(mockPolicy),
  exerciseLibrary: structuredClone(DEFAULT_EXERCISES),
  contentEntries: [],
  packages: DEFAULT_PACKAGES.map(item => ({ ...item })),
  users: [
    { id: 'u-owner', name: 'Chau', role: 'owner', status: 'active' },
    { id: 'u-marcus', name: 'Marcus Tan', role: 'trainer', trainerId: 't1', profile: 'Fully supervised', status: 'active' },
    { id: 'u-aisha', name: 'Aisha Rahman', role: 'trainer', trainerId: 't6', profile: 'Partially autonomous', status: 'active' },
    { id: 'u-daniel', name: 'Daniel Lee', role: 'trainer', trainerId: 't3', profile: 'Fully autonomous', status: 'active' },
  ],

  trainers: [
    {
      id: 't1', status: 'active', name: 'Marcus Tan', phone: '+65 9888 1122', email: 'marcus@fitfinity.sg',
      birthday: '1991-06-14', gender: 'Male', trainerType: 'Strength & Conditioning', qualifications: 'NSCA-CPT, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.marcus,
      monthlyActivity: { sessions: 62, hours: 62, peak: 40, offPeak: 22 }, approvalNeeded: { ...approvals },
    },
    {
      id: 't2', status: 'active', name: 'Rachel Ong', phone: '+65 9771 2233', email: 'rachel@fitfinity.sg',
      birthday: '1993-02-08', gender: 'Female', trainerType: 'Strength & Functional Training', qualifications: 'ACE-CPT, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.rachel,
      monthlyActivity: { sessions: 56, hours: 56, peak: 36, offPeak: 20 }, approvalNeeded: { ...approvals },
    },
    {
      id: 't3', status: 'active', name: 'Daniel Lee', phone: '+65 9662 4488', email: 'daniel@fitfinity.sg',
      birthday: '1989-10-21', gender: 'Male', trainerType: 'Performance & Conditioning', qualifications: 'NASM-CPT, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.daniel,
      monthlyActivity: { sessions: 48, hours: 48, peak: 30, offPeak: 18 },
      approvalNeeded: { availability: false, sessionTime: false, trainerReassignment: false, fixedWeeklySchedule: false },
    },
    {
      id: 't4', status: 'active', name: 'Priya Nair', phone: '+65 9553 7721', email: 'priya@fitfinity.sg',
      birthday: '1992-04-17', gender: 'Female', trainerType: 'Strength & Mobility', qualifications: 'ACE-CPT, Mobility Specialist, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.priya,
      monthlyActivity: { sessions: 46, hours: 46, peak: 29, offPeak: 17 }, approvalNeeded: { ...approvals, sessionTime: false, fixedWeeklySchedule: false },
    },
    {
      id: 't5', status: 'active', name: 'Jerome Goh', phone: '+65 9442 1189', email: 'jerome@fitfinity.sg',
      birthday: '1988-12-02', gender: 'Male', trainerType: 'Fat Loss & Conditioning', qualifications: 'ISSA-CPT, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.jerome,
      monthlyActivity: { sessions: 39, hours: 39, peak: 24, offPeak: 15 }, approvalNeeded: { ...approvals, trainerReassignment: false },
    },
    {
      id: 't6', status: 'active', name: 'Aisha Rahman', phone: '+65 9331 5560', email: 'aisha@fitfinity.sg',
      birthday: '1994-08-29', gender: 'Female', trainerType: 'Mobility & General Fitness', qualifications: 'ACE-CPT, CPR/AED', publicProfile: 'Visible',
      rates: { peak: 80, offPeak: 55 }, availability: availability.aisha,
      monthlyActivity: { sessions: 36, hours: 36, peak: 22, offPeak: 14 }, approvalNeeded: { ...approvals, sessionTime: false, fixedWeeklySchedule: false },
    },
    {
      id: 't7', status: 'active', name: 'Kelvin Chua', phone: '+65 9228 4480', email: 'kelvin@fitfinity.sg',
      birthday: '1990-01-11', gender: 'Male', trainerType: 'Strength', qualifications: 'CPT, CPR/AED', publicProfile: 'Hidden',
      rates: { peak: 80, offPeak: 55 }, availability: availability.kelvin,
      monthlyActivity: { sessions: 31, hours: 31, peak: 19, offPeak: 12 }, approvalNeeded: { ...approvals },
    },
    ...additionalTrainers,
  ],

  clients: allClients,
  sessions: [...featuredSessions, ...generatedCompletedSessions, ...generatedUpcomingSessions],
  packageCreditTransactions: [
    { id: 'credit-s0', type: 'session_debit', sessionId: 's0', clientId: 'c1', amount: -1, createdAt: '2026-08-29T19:03:00+08:00' },
    ...generatedCreditTransactions,
  ],
  messages: [
    {
      id: 'm1', createdAt: '2026-09-01T09:00:00+08:00', recipientRole: 'owner', title: 'Messages foundation ready',
      body: 'Requests and operational updates share one Messages destination.', kind: 'system', read: false,
    },
    {
      id: 'm2', createdAt: '2026-09-01T09:10:00+08:00', recipientTrainerId: 't1', trainerId: 't1', title: 'Trainer messages ready',
      body: 'Approvals, assignments and client-status updates appear here.', kind: 'system', read: false,
    },
    ...initialRenewals.messages,
    ...generatedMessages,
  ],
}

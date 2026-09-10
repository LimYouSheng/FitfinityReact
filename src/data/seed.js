import { mockPolicy } from './mockPolicy.js'
import { DEFAULT_EXERCISES } from './mockExercises.js'
import { DEFAULT_PACKAGES } from './mockPackages.js'
import { appendRenewalMessage } from '../app/renewals.js'
import { updateClientProgress } from '../app/progress.js'
import { addDays, buildClientSessions } from '../app/clientOnboarding.js'

// Drawn evidence for demo records only; existing stored client signatures are never synthesized.
const demoSignature = [[{ x: 60, y: 110 }, { x: 115, y: 62 }, { x: 160, y: 135 }, { x: 245, y: 72 }]]

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
    Thursday: [['18:00', '20:00']], Friday: [['17:00', '19:00']], Saturday: [['08:00', '12:00']], Sunday: [['10:00', '13:00']],
  },
  priya: {
    Monday: [['08:00', '12:00']], Tuesday: [['08:00', '12:00'], ['18:00', '21:00']], Wednesday: [['08:00', '12:00'], ['18:00', '21:00']],
    Thursday: [['18:00', '21:00']], Friday: [['08:00', '12:00']], Saturday: [['09:00', '13:00']], Sunday: [],
  },
  jerome: {
    Monday: [['18:00', '21:00']], Tuesday: [['18:00', '21:00']], Wednesday: [['18:00', '21:00']],
    Thursday: [['18:00', '21:00']], Friday: [['18:00', '20:00']], Saturday: [['10:00', '14:00']], Sunday: [['10:00', '13:00']],
  },
  aisha: {
    Monday: [['09:00', '13:00']], Tuesday: [['18:00', '21:00']], Wednesday: [['09:00', '13:00'], ['18:00', '21:00']],
    Thursday: [['18:00', '21:00']], Friday: [['09:00', '13:00']], Saturday: [['09:00', '12:00']], Sunday: [],
  },
  kelvin: {
    Monday: [['18:00', '20:00']], Tuesday: [['18:00', '20:00']], Wednesday: [['18:00', '20:00']],
    Thursday: [['18:00', '20:00']], Friday: [['18:00', '20:00']], Saturday: [['08:00', '11:00']], Sunday: [['10:00', '13:00']],
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

const baseClients = [
  {
    id: 'c1', status: 'active', type: 'Individual', name: 'Amanda Lim',
    phone: { countryCode: '+65', number: '9123 4567' }, email: 'amanda@example.com', birthday: '1994-04-12', gender: 'Female',
    emergencyContact: { name: 'Jason Lim', relationship: 'Spouse', countryCode: '+65', number: '9000 1122' }, trainerId: 't1',
    genderPreference: 'No gender preference',
    healthNotes: 'Previous right-knee discomfort. Check current symptoms before lower-body loading. Avoid sudden high-impact volume increases.',
    remarks: 'Prefers evening sessions. Keep progression gradual and review goals at renewal.',
    fixedWeeklySchedule: [
      { id: 'slot1', day: 'Monday', from: '18:00', to: '19:00' },
    ],
    package: { durationWeeks: 12, sessionsPerWeek: 1, total: 12, used: 3, validityDays: 90 },
  },
  {
    id: 'c2', status: 'active', type: 'Couple', name: 'Daniel & Mei Wong',
    phone: { countryCode: '+65', number: '9234 8899' }, email: 'wong@example.com', birthday: '1990-03-04', gender: 'Couple',
    emergencyContact: { name: 'Mei Wong', relationship: 'Partner', countryCode: '+65', number: '9001 2200' }, trainerId: 't6',
    genderPreference: 'No gender preference', healthNotes: 'Daniel: shoulder history. Mei: no current limitations.',
    remarks: 'Weekend sessions preferred.',
    fixedWeeklySchedule: [{ id: 'slot3', day: 'Wednesday', from: '19:00', to: '20:00' }, { id: 'slot3b', day: 'Saturday', from: '10:00', to: '11:00' }],
    package: { durationWeeks: 12, sessionsPerWeek: 2, total: 24, used: 7, validityDays: 90 },
  },
  {
    id: 'c3', status: 'active', type: 'Individual', name: 'Nadia Koh',
    phone: { countryCode: '+65', number: '9345 7788' }, email: 'nadia@example.com', birthday: '1988-11-19', gender: 'Female',
    emergencyContact: { name: 'Eric Koh', relationship: 'Sibling', countryCode: '+65', number: '9012 7788' }, trainerId: 't4',
    genderPreference: 'Female trainer preferred', healthNotes: 'No current limitations.', remarks: 'Early weekday sessions.',
    fixedWeeklySchedule: [{ id: 'slot4', day: 'Tuesday', from: '08:00', to: '09:00' }],
    package: { durationWeeks: 12, sessionsPerWeek: 1, total: 12, used: 10, validityDays: 90 },
  },
  {
    id: 'c4', status: 'active', type: 'Individual', name: 'Farah Noor',
    phone: { countryCode: '+65', number: '9455 3301' }, email: 'farah@example.com', birthday: '1996-05-20', gender: 'Female',
    emergencyContact: { name: 'Noor Aziz', relationship: 'Parent', countryCode: '+65', number: '9008 1110' }, trainerId: 't2',
    genderPreference: 'Female trainer preferred', healthNotes: 'No current limitations.', remarks: 'Saturday mornings preferred.',
    fixedWeeklySchedule: [{ id: 'slot5', day: 'Saturday', from: '09:00', to: '10:00' }],
    package: { durationWeeks: 12, sessionsPerWeek: 1, total: 12, used: 4, validityDays: 90 },
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
    trainerId,
    genderPreference: 'No gender preference',
    healthNotes: index % 4 === 0 ? 'Monitor lower-back comfort during loaded hinging.' : 'No current limitations.',
    remarks: index % 2 === 0 ? 'Prefers weekday evening sessions.' : 'Prefers weekend morning sessions.',
    fixedWeeklySchedule: [{
      id: `${id}-slot-1`, day: index % 2 === 0 ? 'Wednesday' : 'Saturday',
      from: index === 8 ? '18:00' : index === 9 ? '11:00' : index % 2 === 0 ? '19:00' : '10:00',
      to: index === 8 ? '19:00' : index === 9 ? '12:00' : index % 2 === 0 ? '20:00' : '11:00',
    }, ...(sessionsPerWeek === 2 ? [{ id: `${id}-slot-2`, day: 'Sunday', from: index === 8 ? '11:00' : '10:00', to: index === 8 ? '12:00' : '11:00' }] : [])],
    package: { durationWeeks: 12, sessionsPerWeek, total, used, validityDays: 90 },
  }
})

// Build a fresh demo around a supplied business date; persisted records never move on reload.
export function createDemoSeed(referenceDate) {
  // Every booking uses the production weekly scheduler.
  const allClients = [...baseClients, ...additionalClients].map(source => {
    const client = structuredClone(source)
    const past = buildClientSessions({ ...client, package: { ...client.package, id: `client-package-${client.id}`, startDate: addDays(referenceDate, -180), total: 366, validityDays: 181 } })
      .filter(session => session.date < referenceDate).slice(-client.package.used)
    client.package = { ...client.package, id: `client-package-${client.id}`, trainerId: client.trainerId,
      startDate: past[0].date, endDate: addDays(past[0].date, client.package.validityDays - 1),
      fixedWeeklySchedule: structuredClone(client.fixedWeeklySchedule) }
    client.lastTrained = past.at(-1).date
    client.packageHistory = [0, 1].map(index => {
      const endDate = addDays(client.package.startDate, -1 - index * 90)
      const total = index ? 12 : client.package.total
      return { id: `${client.id}-package-${index ? '2025-2' : '2026-1'}`, total, used: total, trainerId: client.trainerId, startDate: addDays(endDate, -89), endDate, validityDays: 90 }
    })
    client.startDate = client.packageHistory.at(-1)?.startDate ?? client.package.startDate
    return client
  })
  const scheduledByClient = new Map(allClients.map(client => [client.id, buildClientSessions(client)]))

  const exerciseTemplates = [
    ['Goblet Squat', '16 kg', '10', '3', '60 sec'],
    ['Seated Cable Row', '24 kg', '12', '3', '60 sec'],
    ['DB Chest Press', '10 kg', '10', '3', '75 sec'],
    ['Romanian Deadlift', '30 kg', '8', '4', '90 sec'],
    ['Lat Pulldown', '28 kg', '12', '3', '60 sec'],
    ['Walking Lunge', '8 kg', '20', '3', '60 sec'],
  ]

  // Every demo booking repeats the same set; only recorded loads progress with chronology.
  const plannedExercises = (sessionId, sessionsUntilLatest = 0) => exerciseTemplates.map(([name, weight, reps, rounds, rest], step) => {
    return {
      id: `${sessionId}-exercise-${step + 1}`,
      name,
      weight: `${Math.max(Number.parseFloat(weight) / 2, Number.parseFloat(weight) - sessionsUntilLatest)} kg`,
      reps,
      rounds,
      rest,
      customDetails: name === 'Walking Lunge' ? [{ id: `${sessionId}-detail-1`, value: '10 repetitions per side (20 total)' }] : step === 0 ? [{ id: `${sessionId}-detail-1`, value: 'Controlled tempo' }] : [],
      videoAttached: false,
    }
  })

  // Named examples retain stable IDs; dates/times come only from the weekly schedule.
  const featuredBySlot = {
    c1: { 3: 's0', 4: 's1', 5: 's2' },
    c2: { 8: 's3' },
    c3: { 11: 's5', 12: 's6' },
    c4: { 5: 's4' },
  }
  const seedSessions = allClients.flatMap(client => scheduledByClient.get(client.id)
    .filter(booking => client.status !== 'inactive' || booking.sessionNumber <= client.package.used)
    .map(booking => {
      const completed = booking.sessionNumber <= client.package.used
      const id = featuredBySlot[client.id]?.[booking.sessionNumber] ?? `${completed ? 'history' : 'upcoming'}-${client.id}-${booking.sessionNumber}`
      return { ...booking, id, status: completed ? 'completed' : 'planned',
        exercisePlan: plannedExercises(id, completed ? client.package.used - booking.sessionNumber : 0),
        ...(completed || id === 's1' ? { outcome: { durationMinutes: 60, trainerComments: 'Completed as planned with consistent technique.' } } : {}),
        ...(completed ? {
          acknowledgement: { method: 'signature', signerName: client.name, signature: structuredClone(demoSignature), note: '', recordedAt: `${booking.date}T${booking.to}:00+08:00` },
          whatsappOpenedAt: `${booking.date}T${booking.to}:05+08:00`,
        } : {}),
      }
    }))
    .sort((a, b) => (/^s\d+$/.test(a.id) ? Number(a.id.slice(1)) : 7) - (/^s\d+$/.test(b.id) ? Number(b.id.slice(1)) : 7))
  const seedClients = allClients.map(source => {
    const client = structuredClone(source)
    updateClientProgress({ clients: [client], sessions: seedSessions }, client.id)
    return client
  })

  const generatedCreditTransactions = seedSessions.filter(session => session.status === 'completed').map(session => ({
    id: `credit-${session.id}`, type: 'session_debit', sessionId: session.id, clientId: session.clientId,
    packageId: session.packageId, amount: -1, createdAt: session.acknowledgement.recordedAt,
  }))

  const generatedMessages = allClients.slice(0, 12).map((client, index) => ({
    id: `demo-message-${index + 1}`,
    createdAt: `${client.lastTrained}T21:00:00+08:00`,
    recipientRole: 'owner',
    clientId: client.id,
    trainerId: client.trainerId,
    title: `Session update: ${client.name}`,
    body: `${client.name}'s latest session record is ready for review.`,
    kind: 'session',
    read: index > 4,
  }))

  const initialRenewals = { settings: mockPolicy, messages: [] }
  for (const client of seedClients) {
    const message = appendRenewalMessage(initialRenewals, client, `${referenceDate}T00:00:00+08:00`)
    // Preserve the original demo record's identity for saved read state and routes.
    if (message && client.id === 'c3') message.id = 'm3'
  }

  return {
    demoReferenceDate: referenceDate,
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

    clients: seedClients,
    sessions: seedSessions,
    packageCreditTransactions: generatedCreditTransactions,
    messages: [
      {
        id: 'm1', createdAt: `${addDays(referenceDate, -1)}T09:00:00+08:00`, recipientRole: 'owner', title: 'Messages foundation ready',
        body: 'Requests and operational updates share one Messages destination.', kind: 'system', read: false,
      },
      {
        id: 'm2', createdAt: `${addDays(referenceDate, -1)}T09:10:00+08:00`, recipientTrainerId: 't1', trainerId: 't1', title: 'Trainer messages ready',
        body: 'Approvals, assignments and client-status updates appear here.', kind: 'system', read: false,
      },
      ...initialRenewals.messages,
      ...generatedMessages,
    ],
  }
}

// Deterministic reference fixture; the mock adapter supplies today for new/reset demos.
export const seed = createDemoSeed('2026-09-02')

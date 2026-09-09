import { EXERCISE_LIBRARY } from './mockExercises.js'

// Initial mock configuration. The portal adapter supplies this contract to consumers.
export const mockPolicy = {
  timeZone: 'Asia/Singapore', currency: 'SGD', locale: 'en-SG',
  packageValidity: { 12: 90, 24: 180, 36: 270 },
  packageSessionCount: { minimum: 1, maximum: 365 },
  renewal: { remainingSessions: 2 },
  videoRetentionDays: 7,
  packageValidityRule: { sessions: 12, days: 90 },
  weeklyFrequencies: [1, 2, 3, 4, 5, 6, 7], freeGymMinimumFrequency: 2,
  availability: { from: '18:00', to: '19:00' },
  defaultCountryCode: '+65', defaultRelationship: 'Spouse',
  trainerTypes: ['Strength & Conditioning', 'Personal Trainer'],
  trainerRates: { peak: 80, offPeak: 55 },
  approvalDefaults: { availability: true, sessionTime: true, trainerReassignment: true, fixedWeeklySchedule: true },
  exerciseDefaults: { reps: '8', rounds: '2', rest: '60 sec' },
  exerciseCategories: Object.keys(EXERCISE_LIBRARY),
  password: { minimumLength: 12, maximumLength: 128 },
  sessionHours: 8,
  remuneration: { cycleEndDay: 15, payoutDay: 16, weekendDays: [0, 6], peakWindows: [[390, 510], [1080, 1230]] },
}

export const mockAccountPassword = 'FitfinityDemo1!'

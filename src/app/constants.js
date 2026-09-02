export const OWNER_NAV = [
  { key: 'dashboard', label: 'Dashboard', group: 'Operations' },
  { key: 'clients', label: 'Clients', group: 'Operations' },
  { key: 'trainers', label: 'Trainers', group: 'Operations' },
  { key: 'sessions', label: 'All Sessions', group: 'Operations', disabled: true },

  { key: 'messages', label: 'Messages', group: 'Messages' },

  { key: 'remuneration', label: 'Remuneration', group: 'Remuneration', disabled: true },

  { key: 'exercises', label: 'Exercise Library', group: 'Management', disabled: true },
  { key: 'content', label: 'Content Management', group: 'Management', disabled: true },
]

export const TRAINER_NAV = [
  { key: 'dashboard', label: 'Dashboard', group: 'Trainer' },
  { key: 'clients', label: 'All Clients', group: 'Trainer' },
  { key: 'sessions', label: 'All Sessions', group: 'Trainer', disabled: true },

  { key: 'messages', label: 'Messages', group: 'Messages' },

  { key: 'remuneration', label: 'Remuneration', group: 'Remuneration', disabled: true },
]

export const APPROVAL_FIELDS = [
  ['availability', 'Availability changes'],
  ['sessionTime', 'Session time changes'],
  ['trainerReassignment', 'Trainer reassignment'],
  ['fixedWeeklySchedule', 'Fixed weekly schedule changes'],
]

export const DAYS = [
  'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
]

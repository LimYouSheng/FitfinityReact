import { businessNow } from './scheduleChanges.js'

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/
const iso = date => date.toISOString().slice(0, 10)
export const remunerationBands = { peak: 'Peak', offPeak: 'Off-peak' }
export const formatMoney = (cents, policy) => new Intl.NumberFormat(policy.locale, { style: 'currency', currency: policy.currency }).format(cents / 100)

export function payCycle(key, policy) {
  if (!MONTH.test(key ?? '')) throw new Error('Choose a valid pay cycle.')
  const [year, month] = key.split('-').map(Number)
  return { key, start: iso(new Date(Date.UTC(year, month - 2, policy.cycleEndDay + 1))), end: `${key}-${String(policy.cycleEndDay).padStart(2, '0')}`, payout: `${key}-${String(policy.payoutDay).padStart(2, '0')}` }
}

export function cycleForDate(date, policy) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date ?? '')) return null
  const value = new Date(`${date}T00:00:00Z`)
  if (!Number.isFinite(value.getTime()) || iso(value) !== date) return null
  return iso(new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + (value.getUTCDate() > policy.cycleEndDay ? 1 : 0), 1))).slice(0, 7)
}

// Dates and times are the stored Singapore calendar date and local start time.
// Peak windows include their start and exclude their end; the whole session
// takes its start-time band, without splitting or prorating the session rate.
export function sessionRateBand(session, policy) {
  if (!cycleForDate(session.date, policy) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(session.from ?? '')) return null
  const day = new Date(`${session.date}T00:00:00Z`).getUTCDay()
  if (policy.weekendDays.includes(day)) return 'peak'
  const [hour, minute] = session.from.split(':').map(Number)
  const start = hour * 60 + minute
  return policy.peakWindows.some(([from, to]) => start >= from && start < to) ? 'peak' : 'offPeak'
}

// Keep the completed-session evidence alongside approved amounts.
export function sessionPaySource(session) {
  const evidence = [session.id, session.clientId, session.trainerId, session.date, session.from, session.to, session.status,
    session.outcome?.durationMinutes ?? null, session.acknowledgement?.method ?? null,
    session.acknowledgement?.signerName ?? null, session.acknowledgement?.note ?? null, session.acknowledgement?.recordedAt ?? null, session.acknowledgement?.signature ?? null]
  if (session.acknowledgementHistory?.length) evidence.push(session.acknowledgementHistory)
  return JSON.stringify(evidence)
}

export function rateCents(trainer, band) {
  const value = trainer?.rates?.[band]
  if (!Object.hasOwn(remunerationBands, band) || typeof value !== 'number' || !Number.isFinite(value) || value < 0 || !Number.isSafeInteger(Math.round(value * 100)) || Math.abs(value * 100 - Math.round(value * 100)) > 1e-6) return null
  return Math.round(value * 100)
}

function durationMinutes(session) {
  const duration = session.outcome?.durationMinutes
  if (typeof duration === 'number' && Number.isFinite(duration) && (duration > 0 || (duration === 0 && session.acknowledgement?.method === 'late_no_show'))) return duration
  if (session.acknowledgement?.method === 'late_no_show') return 0
  const minutes = value => /^([01]\d|2[0-3]):[0-5]\d$/.test(value ?? '') ? Number(value.slice(0, 2)) * 60 + Number(value.slice(3)) : null
  const start = minutes(session.from), end = minutes(session.to)
  return start !== null && end !== null && end > start ? end - start : 0
}

export function remunerationDraft(db, key, trainerId, now = new Date()) {
  const policy = db.settings.remuneration
  const cycle = payCycle(key, policy)
  const trainer = db.trainers.find(item => item.id === trainerId)
  if (!trainer) throw new Error('Trainer not found.')
  const today = businessNow(now, db.settings.timeZone).date
  const rows = (db.sessions ?? []).filter(session => session.trainerId === trainerId && session.status !== 'cancelled' && cycleForDate(session.date, policy) === key)
    .sort((a, b) => `${a.date}|${a.from}|${a.id}`.localeCompare(`${b.date}|${b.from}|${b.id}`))
    .map(session => {
      const source = sessionPaySource(session)
      const band = sessionRateBand(session, policy)
      const amount = rateCents(trainer, band)
      // Completion is committed by the acknowledgement operation. Remuneration
      // consumes that state without revalidating the signature or WhatsApp.
      const completed = session.status === 'completed'
      const billable = completed && session.date <= today
      const issues = [!band ? 'Invalid session start time' : amount === null && 'Missing trainer rate', !completed && 'Session is not completed', completed && session.date > today && 'Future completion date'].filter(Boolean)
      const client = db.clients.find(item => item.id === session.clientId)
      return { sessionId: session.id, source, clientId: session.clientId, clientName: client?.name ?? 'Client unavailable', clientType: client?.type ?? '—', date: session.date,
        from: session.from, to: session.to, durationMinutes: billable ? durationMinutes(session) : 0, status: session.status, billable,
        band: band ?? '', amountCents: billable ? amount : null, issues }
    })
  const reviewCount = rows.filter(row => row.issues.length).length
  const amountCents = rows.reduce((total, row) => total + (row.amountCents ?? 0), 0)
  const closed = today > cycle.end
  const status = !closed ? 'In progress' : !rows.length ? 'No sessions' : reviewCount ? 'Pending review' : 'Pending approval'
  const result = { cycle, trainerId, trainerName: trainer.name, rows, sessions: rows.filter(row => row.billable).length, totalSessions: rows.length, minutes: rows.reduce((total, row) => total + row.durationMinutes, 0), amountCents, reviewCount, closed, status }
  // Include rates and all billable evidence so stale pages cannot silently approve new amounts.
  result.revision = JSON.stringify([key, trainerId, trainer.name, trainer.rates, rows])
  return result
}

export function remunerationRecord(db, key, trainerId, now = new Date()) {
  const current = remunerationDraft(db, key, trainerId, now)
  const approved = (db.remunerationApprovals ?? []).find(record => record.cycle.key === key && record.trainerId === trainerId)
  if (!approved) return current
  // Approved amounts stay fixed, including approvals made before automatic bands.
  // Only changes to session evidence flag the approved record for review.
  const evidence = rows => rows.map(row => [row.sessionId, row.source]).sort(([a], [b]) => a.localeCompare(b))
  const changed = JSON.stringify(evidence(current.rows)) !== JSON.stringify(evidence(approved.rows))
  return { ...approved, status: 'Approved', reviewCount: 0, changed, current, closed: true }
}

export function remunerationCycles(db, user, now = new Date()) {
  const policy = db.settings.remuneration
  const keys = new Set([cycleForDate(businessNow(now, db.settings.timeZone).date, policy)])
  for (const session of db.sessions ?? []) {
    if (session.status !== 'cancelled' && (user.role === 'owner' || session.trainerId === user.trainerId)) keys.add(cycleForDate(session.date, policy))
  }
  for (const record of db.remunerationApprovals ?? []) {
    if (user.role === 'owner' || record.trainerId === user.trainerId) keys.add(record.cycle.key)
  }
  return [...keys].filter(key => MONTH.test(key ?? '')).sort().reverse()
}

export function cycleTrainers(db, key, user, now = new Date()) {
  return db.trainers.filter(trainer => user.role === 'owner' || trainer.id === user.trainerId)
    .map(trainer => remunerationRecord(db, key, trainer.id, now))
    .filter(record => record.rows.length || (db.trainers.find(trainer => trainer.id === record.trainerId)?.status ?? 'active') === 'active')
    .sort((a, b) => a.trainerName.localeCompare(b.trainerName))
}

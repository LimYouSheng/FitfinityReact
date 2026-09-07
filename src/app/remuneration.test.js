import { describe, expect, it } from 'vitest'
import { cycleForDate, cycleTrainers, payCycle, rateCents, remunerationDraft, remunerationRecord, sessionPaySource, sessionRateBand } from './remuneration.js'
import { payFixture } from '../test/fixtures/remuneration.js'
const now = new Date('2026-09-16T00:00:00Z')
describe('monthly remuneration', () => {
  it('assigns the 15th and 16th to distinct cycles, including December rollover and leap years', () => {
    expect(cycleForDate('2026-09-15')).toBe('2026-09')
    expect(cycleForDate('2026-09-16')).toBe('2026-10')
    expect(cycleForDate('2026-12-16')).toBe('2027-01')
    expect(payCycle('2027-01')).toEqual({ key: '2027-01', start: '2026-12-16', end: '2027-01-15', payout: '2027-01-16' })
    expect(cycleForDate('2028-02-29')).toBe('2028-03')
    expect(cycleForDate('2026-02-29')).toBeNull()
    expect(() => payCycle('2026-13')).toThrow()
  })
  it('includes only completed sessions within the cycle and calculates their rates automatically', () => {
    const db = payFixture()
    db.sessions.push(...['planned', 'cancelled'].map(status => ({ ...db.sessions[0], id: status, status })), { ...db.sessions[0], id: 'old', date: '2026-08-15' })
    const record = remunerationDraft(db, '2026-09', 't1', now)
    expect(record.sessions).toBe(1)
    expect(record.amountCents).toBe(8000)
    expect(record.status).toBe('Pending approval')
    expect(record.rows[0]).toMatchObject({ band: 'peak', issues: [] })
    expect(db.remunerationEntries).toBeUndefined()
  })
  it('uses the session start band without prorating duration and recalculates changed session times', () => {
    const db = payFixture()
    db.sessions[0].from = '08:00'; db.sessions[0].to = '09:30'; db.sessions[0].outcome.durationMinutes = 90
    expect(remunerationDraft(db, '2026-09', 't1', now)).toMatchObject({ amountCents: 8000, minutes: 90, reviewCount: 0 })
    db.sessions[0].from = '08:30'; db.sessions[0].to = '10:00'
    expect(remunerationDraft(db, '2026-09', 't1', now)).toMatchObject({ amountCents: 5500, minutes: 90, reviewCount: 0 })
  })
  it('applies automatic rates to completed late/no-show sessions and still rejects missing acknowledgements', () => {
    const db = payFixture()
    db.sessions[0].acknowledgement = { method: 'late_no_show', recordedAt: '2026-08-20T19:00:00+08:00' }
    db.sessions[0].outcome.durationMinutes = 0
    expect(remunerationDraft(db, '2026-09', 't1', now)).toMatchObject({ amountCents: 8000, reviewCount: 0 })
    delete db.sessions[0].acknowledgement
    expect(remunerationDraft(db, '2026-09', 't1', now).rows[0].issues).toContain('Missing acknowledgement')
  })
  it('retains approved amounts after rate changes and exposes changed session evidence', () => {
    const db = payFixture()
    db.remunerationApprovals = [{ ...remunerationDraft(db, '2026-09', 't1', now), status: 'Approved', approvedAt: now.toISOString() }]
    db.trainers[0].rates.peak = 100
    expect(remunerationRecord(db, '2026-09', 't1', now)).toMatchObject({ amountCents: 8000, changed: false, current: { amountCents: 10000 } })
    db.sessions[0].status = 'cancelled'
    expect(remunerationRecord(db, '2026-09', 't1', now)).toMatchObject({ sessions: 1, amountCents: 8000, changed: true, current: { sessions: 0 } })
  })
  it('scopes trainers to their own records and retains inactive trainer earnings for the owner', () => {
    const db = payFixture()
    db.trainers[0].status = 'inactive'
    expect(cycleTrainers(db, '2026-09', { role: 'trainer', trainerId: 't2' }, now).map(record => record.trainerId)).toEqual(['t2'])
    expect(cycleTrainers(db, '2026-09', { role: 'owner' }, now).map(record => record.trainerId)).toEqual(['t1', 't2'])
  })
  it('validates money precision and handles the Singapore payout date boundary', () => {
    expect(rateCents({ rates: { peak: 80.25 } }, 'peak')).toBe(8025)
    for (const peak of [NaN, Infinity, -1, '80', 80.255]) expect(rateCents({ rates: { peak } }, 'peak')).toBeNull()
    const db = payFixture()
    expect(remunerationDraft(db, '2026-09', 't1', new Date('2026-09-15T15:59:59Z')).closed).toBe(false)
    expect(remunerationDraft(db, '2026-09', 't1', new Date('2026-09-15T16:00:00Z')).closed).toBe(true)
  })
  it('includes weekday peak starts and excludes the morning and evening end times', () => {
    const cases = { '00:00': 'offPeak', '06:29': 'offPeak', '06:30': 'peak', '08:29': 'peak', '08:30': 'offPeak', '17:59': 'offPeak', '18:00': 'peak', '20:29': 'peak', '20:30': 'offPeak', '23:59': 'offPeak' }
    for (const [from, band] of Object.entries(cases)) expect(sessionRateBand({ date: '2026-09-04', from }), from).toBe(band)
  })
  it('treats Saturday and Sunday as peak all day using the stored Singapore date', () => {
    for (const date of ['2026-09-05', '2026-09-06']) {
      for (const from of ['00:00', '08:30', '12:00', '20:30', '23:59']) expect(sessionRateBand({ date, from }), `${date} ${from}`).toBe('peak')
    }
    expect(sessionRateBand({ date: '2026-09-07', from: '00:00' })).toBe('offPeak')
  })
  it('uses trainer presets and ignores superseded manual rate decisions for unapproved cycles', () => {
    const db = payFixture()
    db.trainers[0].rates = { peak: 90.5, offPeak: 60 }
    db.remunerationEntries = [{ sessionId: 'pay1', source: sessionPaySource(db.sessions[0]), band: 'notPayable', rateCents: 0 }]
    expect(remunerationDraft(db, '2026-09', 't1', now)).toMatchObject({ amountCents: 9050, reviewCount: 0 })
    db.sessions[0].from = '10:00'; db.sessions[0].to = '11:00'
    expect(remunerationDraft(db, '2026-09', 't1', now)).toMatchObject({ amountCents: 6000, reviewCount: 0 })
  })
  it('keeps malformed times and missing trainer rates unresolved instead of guessing a band or amount', () => {
    for (const from of ['', '25:00', '6:30', '18:60']) expect(sessionRateBand({ date: '2026-09-05', from })).toBeNull()
    expect(sessionRateBand({ date: '2026-02-30', from: '18:00' })).toBeNull()
    const db = payFixture()
    db.sessions[0].from = 'bad'
    expect(remunerationDraft(db, '2026-09', 't1', now).rows[0]).toMatchObject({ band: '', amountCents: null, issues: ['Invalid session start time'] })
    db.sessions[0].from = '18:00'; delete db.trainers[0].rates.peak
    expect(remunerationDraft(db, '2026-09', 't1', now).rows[0]).toMatchObject({ band: 'peak', amountCents: null, issues: ['Missing trainer rate'] })
  })
  it('preserves legacy approval snapshots without treating the new pricing rules as a session edit', () => {
    const db = payFixture()
    const legacy = remunerationDraft(db, '2026-09', 't1', now)
    legacy.rows[0].band = 'offPeak'; legacy.rows[0].amountCents = 5500; legacy.amountCents = 5500
    db.remunerationApprovals = [{ ...legacy, status: 'Approved', approvedAt: now.toISOString() }]
    expect(remunerationRecord(db, '2026-09', 't1', now)).toMatchObject({ amountCents: 5500, changed: false, current: { amountCents: 8000 } })
    db.sessions[0].from = '19:00'
    expect(remunerationRecord(db, '2026-09', 't1', now).changed).toBe(true)
  })
})

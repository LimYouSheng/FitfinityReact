import { describe, expect, it } from 'vitest'
import { businessClock } from './clock.js'
import { calendarDays, calendarSessions, shiftCalendarDate } from './calendar.js'
import { validSignature } from './signature.js'
import { updateClientProgress, validateExerciseResults } from './progress.js'
import { packageFor } from './clientOnboarding.js'
import { payCycle, sessionRateBand } from './remuneration.js'
import { signatureFixture } from '../test/fixtures/signature.js'

describe('M4 data-driven domain behavior', () => {
  it('uses the supplied business timezone across midnight and leap-day calendar boundaries', () => {
    expect(businessClock(new Date('2032-02-28T16:01:00Z'), 'Asia/Singapore').date).toBe('2032-02-29')
    expect(businessClock(new Date('2032-02-28T16:01:00Z'), 'UTC').date).toBe('2032-02-28')
    expect(calendarDays('2032-02-29', 'week')).toHaveLength(7)
    expect(calendarDays('2032-02-29', 'month')).toContain('2032-02-29')
    expect(calendarDays('2032-02-29', 'month')).toHaveLength(42)
    expect(shiftCalendarDate('2032-12-31', 1, 'month')).toBe('2033-01-01')
  })
  it('selects only calendar records in the requested range and sorts same-day sessions', () => {
    const sessions = [{ id: 'b', date: '2032-02-29', from: '19:00' }, { id: 'c', date: '2032-03-09', from: '17:00' }, { id: 'a', date: '2032-02-29', from: '08:00' }]
    expect(calendarSessions(sessions, calendarDays('2032-02-29', 'week')).map(item => item.id)).toEqual(['a', 'b'])
  })
  it('rejects blank, single-click, malformed and oversized signatures', () => {
    expect(validSignature(signatureFixture)).toBe(true)
    for (const invalid of [[], [[{x:1,y:1}]], [[{x:1,y:1},{x:1,y:1},{x:1,y:1}]], [[{x:Infinity,y:2}]], Array(101).fill(signatureFixture[0])]) expect(validSignature(invalid)).toBe(false)
  })
  it('records measured loads only and updates one progress point after corrections', () => {
    const rows = validateExerciseResults([{ id: 'a', name: 'Row', loadKg: '0', reps: '8', sets: '2' }, {id:'b',name:'Squat',loadKg:'',reps:'8',sets:'2'}])
    const db = { clients: [{ id: 'client', strengthProgress: [] }], sessions: [{ id: 'session',clientId:'client',date:'2032-02-29',status:'planned',exerciseResults:rows }] }
    updateClientProgress(db,'client'); expect(db.clients[0].strengthProgress).toEqual([])
    db.sessions[0].status='completed'; updateClientProgress(db,'client'); updateClientProgress(db,'client')
    expect(db.clients[0].strengthProgress[0].points).toHaveLength(1)
    expect(db.clients[0].strengthProgress[0].points[0].load).toBe(0)
    db.sessions[0].exerciseResults[0].loadKg=25; updateClientProgress(db,'client')
    expect(db.clients[0].strengthProgress[0].points[0].load).toBe(25)
    expect(() => validateExerciseResults([{id:'bad',name:'Row',loadKg:-1,reps:8,sets:2}])).toThrow()
  })
  it('accepts changed package and remuneration policy without changing screens', () => {
    expect(packageFor('2032-03-01', 2, {total:18,validityDays:60},3)).toMatchObject({total:18,validityDays:60,freeGym:false})
    const rules={cycleEndDay:20,payoutDay:21,weekendDays:[],peakWindows:[[600,660]]}
    expect(payCycle('2032-03',rules)).toMatchObject({start:'2032-02-21',end:'2032-03-20',payout:'2032-03-21'})
    expect(sessionRateBand({date:'2032-03-01',from:'10:30'},rules)).toBe('peak')
    expect(sessionRateBand({date:'2032-03-01',from:'18:30'},rules)).toBe('offPeak')
  })
})

import { expect, it, vi } from 'vitest'
import { sessionCalendar, sessionDetail } from './apiSessionReads.js'
import { createConfiguredPortalServices } from './defaultPortalServices.js'
import { authPolicy, failure, jsonResponse, sessionInfo, staff } from '../test/api.js'
import { directoryData, directoryId } from '../test/directory.js'
import { calendarData, sessionDetailData } from '../test/sessionReads.js'
it('loads persisted calendars and configured session details without a write or profile promotion', async () => {
  const directory = { ...directoryData(), sessionReads: true, personalMessages: true }
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : url.endsWith('/policy') ? authPolicy : url.endsWith('/directory') ? directory : url.endsWith('/session-calendar') ? calendarData() : url.endsWith('/details') ? sessionDetailData() : []))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch })
  const snapshot = await services.load()
  expect(snapshot.capabilities.sessionReads).toBe(true)
  expect(snapshot.data.sessions[0]).toMatchObject({ id: directoryId(30), status: 'not_planned', date: '2026-10-13' })
  const details = await services.forSession(snapshot.sessionGeneration).readSessionDetails({ id: directoryId(30) })
  expect(details.session.exerciseResults[0].loadKg).toBe(12.5)
  expect(details.session.exercisePlan[0].customDetails[0].value).toBe('Stored instruction')
  expect(details.session.whatsappOpenedAt).toBeNull()
  expect(fetch.mock.calls.every(([, o]) => o.method === 'GET')).toBe(true)
})
it('retains Open sessions with no invented date or position', () => {
  const data = calendarData(); Object.assign(data.sessions[0], { scheduleState: 'open', date: null, startsAt: null, endsAt: null, sessionNumber: null })
  expect(sessionCalendar(data, staff).sessions[0]).toMatchObject({ scheduleState: 'open', date: null, from: null, to: null, sessionNumber: null })
})
it('rejects foreign viewers, another Trainer, missing relations and private fields', () => {
  for (const change of [d => { d.viewerId = directoryId(99) }, d => { d.clients[0].healthNotes = 'private' }, d => { d.trainers[0].rates = {} }, d => { d.sessions[0].purchaseId = directoryId(99) }, d => { d.clients.push({ ...d.clients[0], id: directoryId(99) }) }]) {
    const data = calendarData(); change(data)
    expect(() => sessionCalendar(data, staff)).toThrow('could not be verified')
  }
  expect(() => sessionCalendar(calendarData(), { ...staff, role: 'trainer', trainerId: directoryId(99) })).toThrow('could not be verified')
})
it('rejects unknown states, inconsistent Open fields and duplicate identities', () => {
  for (const change of [d => { d.sessions[0].status = 'assumed' }, d => { d.sessions[0].scheduleState = 'open' }, d => { d.sessions.push(d.sessions[0]) }, d => { d.purchases[0].used = 13 }]) {
    const data = calendarData(); change(data)
    expect(() => sessionCalendar(data, staff)).toThrow('could not be verified')
  }
})
it('validates exact detail identity, result relations, signatures and private response fields', () => {
  for (const change of [d => { d.session.id = directoryId(99) }, d => { d.exerciseResults[0].planItemId = directoryId(99) }, d => { d.client.people = [] }, d => { d.exercisePlan[0].objectKey = 'secret' }, d => { d.acknowledgementHistory = [{ id: directoryId(42), sequence: 1, method: 'signature', signature: [] }] }]) {
    const data = sessionDetailData(); change(data)
    expect(() => sessionDetail(data, directoryId(30), staff)).toThrow('could not be verified')
  }
})
it('retains original signature history and does not fabricate a new acknowledgement', () => {
  const data = sessionDetailData(); data.session.status = 'completed'
  data.acknowledgementHistory = [{ id: directoryId(42), sequence: 1, method: 'late_no_show', signerName: null, signature: null, note: 'Initial', recordedAt: '2026-10-13T10:00:00Z', recordedBy: { id: staff.id, name: staff.name } }, { id: directoryId(43), sequence: 2, method: 'signature', signerName: 'API Client', signature: [[{ x: 10, y: 10 }, { x: 30, y: 30 }, { x: 60, y: 10 }]], note: 'Corrected', recordedAt: '2026-10-13T11:00:00Z', recordedBy: { id: staff.id, name: staff.name } }]
  const result = sessionDetail(data, directoryId(30), staff)
  expect(result.session.acknowledgementHistory).toHaveLength(2)
  expect(result.session.acknowledgement.method).toBe('signature')
  expect(result.session.acknowledgement.recordedBy.id).toBe(staff.id)
})
it('propagates scoped detail denial and never falls back to demo records', async () => {
  const fetch = vi.fn(async url => url.endsWith('/me') ? jsonResponse(sessionInfo()) : failure('not_found', 404))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  await expect(services.readSessionDetails({ id: directoryId(30) })).rejects.toMatchObject({ status: 404 })
  expect(fetch.mock.calls.filter(([, o]) => o.method === 'POST')).toHaveLength(0)
})
it('retains server-authorized historical cover for the original Trainer without granting a full profile', () => {
  const data = calendarData(); data.sessions[0].readAccess = 'historical'
  const user = { ...staff, role: 'trainer', trainerId: directoryId(99) }
  const result = sessionCalendar(data, user)
  expect(result.sessions[0].readableByTrainerId).toBe(directoryId(99))
  expect(result.sessionClients[0]).not.toHaveProperty('people')
})
it('reads active cover client names through the existing scoped endpoint and rejects profile fields', async () => {
  let response = { session_id: directoryId(30), client_id: directoryId(7), name: 'Covered Couple', kind: 'couple', person_names: ['First', 'Second'] }
  const fetch = vi.fn(async url => jsonResponse(url.endsWith('/me') ? sessionInfo() : response))
  const services = createConfiguredPortalServices({ mode: 'api', fetchImpl: fetch }).forSession(0)
  expect((await services.readSessionClient({ id: directoryId(30), clientId: directoryId(7) })).person_names).toEqual(['First', 'Second'])
  response = { ...response, client_id: directoryId(99) }
  await expect(services.readSessionClient({ id: directoryId(30), clientId: directoryId(7) })).rejects.toMatchObject({ code: 'API_RESPONSE' })
  response = { ...response, client_id: directoryId(7), healthNotes: 'private' }
  await expect(services.readSessionClient({ id: directoryId(30), clientId: directoryId(7) })).rejects.toMatchObject({ code: 'API_RESPONSE' })
})
it('retains result identity for a retired plan item without presenting it as the current plan', () => {
  const data = sessionDetailData(), retired = data.exercisePlan[0].id
  data.exercisePlan = []
  data.retiredPlanItemIds = [retired]
  const result = sessionDetail(data, directoryId(30), staff)
  expect(result.session.exercisePlan).toEqual([])
  expect(result.session.exerciseResults[0].id).toBe(retired)
  data.retiredPlanItemIds = [directoryId(99)]
  expect(() => sessionDetail(data, directoryId(30), staff)).toThrow('could not be verified')
})

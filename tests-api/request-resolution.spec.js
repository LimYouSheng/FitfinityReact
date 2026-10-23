import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

/** Create a real supervised proposal; all decisions below are submitted through the UI. */
async function proposal(page, info, purpose, kind) {
  await signIn(page, 'trainer', `${info.project.name}-${purpose}@example.test`)
  const directory = await read(page, '/api/directory')
  expect(directory.clients.map(c => c.name)).toEqual([`${info.project.name} ${purpose}`])
  const client = directory.clients[0], trainer = directory.trainers.find(t => t.id === client.trainer_id)
  const sessions = (await read(page, '/api/session-calendar')).sessions
  expect(sessions.every(s => s.clientId === client.id)).toBe(true)
  let response
  if (kind === 'trainer_availability') {
    response = await post(page, `/api/trainers/${trainer.id}/availability`, { expectedVersion: trainer.version, slots: [{ weekday: 1, startsAt: '09:00', endsAt: '12:00' }] })
  } else if (kind === 'fixed_weekly_schedule') {
    const review = await read(page, `/api/clients/${client.id}/weekly-schedule-review`)
    response = await post(page, `/api/clients/${client.id}/weekly-schedule`, { expected: review.expected, slots: review.slots.map(s => ({ ...s, startsAt: '12:00', endsAt: '13:00' })) })
  } else {
    const review = await read(page, `/api/sessions/${sessions[0].id}/postponement-review`)
    response = await post(page, `/api/sessions/${sessions[0].id}/postponement`, { expected: review.expected })
  }
  expect(response.status()).toBe(200)
  const saved = await response.json()
  expect(saved.outcome).toBe('requested')
  expect((await post(page, `/api/requests/${saved.requestId}/resolve`, { expectedVersion: 1, decision: 'approved' })).status()).toBe(403)
  return { client, trainer, sessions, id: saved.requestId }
}
async function review(page, id) {
  const message = (await read(page, '/api/messages')).find(m => m.requestId === id)
  expect(message.request.status).toBe('pending')
  await page.getByRole('banner').getByRole('button', { name: 'Messages', exact: true }).click()
  await page.getByRole('button', { name: `Open ${message.title}`, exact: true }).click()
  await expect(page.getByRole('region', { name: 'Requested change' })).toBeVisible()
}
async function decide(page, approved = true) {
  const label = approved ? 'Approve Request' : 'Reject Request'
  await page.getByRole('button', { name: label, exact: true }).click()
  await page.getByRole('dialog', { name: approved ? 'Approve request?' : 'Reject request?', exact: true }).getByRole('button', { name: label, exact: true }).click()
}
async function assertState(page, id, status) {
  await page.reload()
  expect((await read(page, '/api/messages')).filter(m => m.requestId === id).every(m => m.request.status === status)).toBe(true)
  expect((await read(page, '/api/messages')).some(m => m.requestId === id && m.kind === 'request_decision')).toBe(true)
}
for (const [purpose, kind] of [['resolveavailability', 'trainer_availability'], ['resolveweekly', 'fixed_weekly_schedule']]) {
  test(`Owner approves ${kind} in UI and a fresh Trainer login sees only the committed scoped change`, async ({ page, browser }, info) => {
    const before = await proposal(page, info, purpose, kind)
    const owner = await freshContext(browser, page), staffPage = await owner.newPage()
    await signIn(staffPage, 'owner', account(purpose))
    const allBefore = (await read(staffPage, '/api/session-calendar')).sessions
    expect(allBefore.some(s => s.clientId !== before.client.id)).toBe(true)
    await review(staffPage, before.id)
    await decide(staffPage)
    await expect(staffPage.getByText('Request approved.', { exact: true })).toBeVisible()
    await assertState(staffPage, before.id, 'approved')
    const allAfter = (await read(staffPage, '/api/session-calendar')).sessions
    expect(allAfter.filter(s => s.clientId !== before.client.id)).toEqual(allBefore.filter(s => s.clientId !== before.client.id))
    const fresh = await freshContext(browser, page), trainerPage = await fresh.newPage()
    await signIn(trainerPage, 'trainer', `${info.project.name}-${purpose}@example.test`)
    const saved = await read(trainerPage, '/api/directory')
    expect(saved.clients.map(c => c.id)).toEqual([before.client.id])
    if (kind === 'trainer_availability') {
      expect(saved.trainers.find(t => t.id === before.trainer.id).availability.map(({ weekday, starts_at, ends_at }) => ({ weekday, starts_at, ends_at }))).toEqual([{ weekday: 1, starts_at: '09:00:00', ends_at: '12:00:00' }])
      expect((await read(trainerPage, '/api/session-calendar')).sessions).toEqual(before.sessions)
    } else expect((await read(trainerPage, '/api/session-calendar')).sessions.every(s => s.startsAt === '12:00' && s.endsAt === '13:00')).toBe(true)
    await fresh.close(); await owner.close()
  })
}

test('Admin rejects a postponement proposal through UI without changing any bookings', async ({ page, browser }, info) => {
  const before = await proposal(page, info, 'resolvepostpone', 'session_postpone')
  const admin = await freshContext(browser, page), staffPage = await admin.newPage()
  await signIn(staffPage, 'admin', account('resolvepostpone', 'admin'))
  await review(staffPage, before.id)
  await decide(staffPage, false)
  await expect(staffPage.getByText('Request rejected.', { exact: true })).toBeVisible()
  await assertState(staffPage, before.id, 'rejected')
  expect((await read(page, '/api/session-calendar')).sessions).toEqual(before.sessions)
  await admin.close()
})

test('stale availability approval rejects, then explicit rejection retires the unchanged proposal', async ({ page, browser }, info) => {
  const before = await proposal(page, info, 'resolvestale', 'trainer_availability')
  const owner = await freshContext(browser, page), staffPage = await owner.newPage()
  await signIn(staffPage, 'owner', account('resolvestale'))
  await review(staffPage, before.id)
  const current = (await read(staffPage, '/api/directory')).trainers.find(t => t.id === before.trainer.id)
  expect((await post(staffPage, `/api/trainers/${current.id}/approvals`, { expectedVersion: current.version, approvalNeeded: { availability: false, sessionTime: current.approve_session_time, trainerReassignment: current.approve_session_trainer, fixedWeeklySchedule: current.approve_weekly_schedule } })).status()).toBe(200)
  await decide(staffPage)
  await expect(staffPage.getByRole('region', { name: 'Requested change' }).getByRole('alert')).toBeVisible()
  await decide(staffPage, false)
  await expect(staffPage.getByText('Request rejected.', { exact: true })).toBeVisible()
  await assertState(staffPage, before.id, 'rejected')
  expect((await read(page, '/api/directory')).trainers.find(t => t.id === before.trainer.id).availability).toEqual(before.trainer.availability)
  await owner.close()
})

test('lost committed approval response checks the original decision and never repeats domain effects', async ({ page, browser }, info) => {
  const before = await proposal(page, info, 'resolveloss', 'session_postpone')
  const owner = await freshContext(browser, page), staffPage = await owner.newPage()
  await staffPage.addInitScript(() => {
    const original = window.fetch.bind(window)
    window.decisionWrites = 0
    window.fetch = async (url, options) => {
      const response = await original(url, options)
      if (options?.method === 'POST' && /\/api\/requests\/[^/]+\/resolve$/.test(String(url))) {
        window.decisionWrites++
        window.decisionKey = options.headers['Idempotency-Key']
        if (window.decisionWrites === 1 && response.ok) { await response.clone().text(); throw new TypeError('Lost committed decision response') }
      }
      return response
    }
  })
  await signIn(staffPage, 'owner', account('resolveloss'))
  await review(staffPage, before.id)
  await decide(staffPage)
  await expect(staffPage.getByRole('button', { name: 'Reject Request', exact: true })).toBeDisabled()
  await staffPage.getByRole('button', { name: 'Check Approval', exact: true }).click()
  await expect(staffPage.getByText('Request approved.', { exact: true })).toBeVisible()
  expect(await staffPage.evaluate(() => window.decisionWrites)).toBe(1)
  const key = await staffPage.evaluate(() => window.decisionKey)
  expect((await page.request.get(`/api/request-resolutions/${key}`)).status()).toBe(403)
  await assertState(staffPage, before.id, 'approved')
  const sessions = (await read(page, '/api/session-calendar')).sessions
  expect(sessions.find(s => s.id === before.sessions[0].id)).toMatchObject({ scheduleState: 'open', date: null, startsAt: null, endsAt: null })
  expect(sessions.filter(s => s.scheduleState === 'open')).toHaveLength(1)
  await owner.close()
})

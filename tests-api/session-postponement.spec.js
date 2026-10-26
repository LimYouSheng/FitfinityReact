import { test, expect, signIn, read, post, account } from './fixtures.js'

async function open(page, info, purpose, role = 'owner') {
  await signIn(page, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose))
  const directory = await read(page, '/api/directory')
  const client = directory.clients.find(c => c.name === `${info.project.name} ${purpose}`)
  const calendar = await read(page, '/api/session-calendar')
  const sessions = calendar.sessions.filter(s => s.clientId === client.id).sort((a, b) => a.sessionNumber - b.sessionNumber)
  expect(sessions).toHaveLength(2)
  if (role === 'trainer') expect(calendar.sessions.every(s => s.clientId === client.id && s.readAccess === 'assigned')).toBe(true)
  await page.goto(`/#/sessions/${sessions[0].id}`)
  await expect(page.getByRole('button', { name: 'Postpone', exact: true })).toBeEnabled()
  return { client, sessions }
}
async function preview(page) {
  await page.getByRole('button', { name: 'Postpone', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Postpone this session?', exact: true })
  await expect(dialog.getByRole('table')).toContainText('Open session · Date/time not set')
  return dialog
}
async function confirm(page, dialog) {
  await expect(dialog.getByRole('table')).toContainText('Open session · Date/time not set')
  await dialog.getByRole('button', { name: 'Confirm Postponement', exact: true }).click()
  await expect(dialog).toHaveCount(0)
}
async function assertOpen(page, client, sessions) {
  await page.reload()
  await expect(page.locator('.session-overview-panel')).toContainText('Date/time not set')
  const current = (await read(page, '/api/session-calendar')).sessions.filter(s => s.clientId === client.id)
  expect(current).toHaveLength(2)
  expect(current.find(s => s.id === sessions[0].id)).toMatchObject({ scheduleState: 'open', date: null, startsAt: null, endsAt: null, sessionNumber: null })
  expect(current.find(s => s.id === sessions[1].id)).toMatchObject({ date: sessions[1].date, startsAt: sessions[1].startsAt, endsAt: sessions[1].endsAt, trainerId: sessions[1].trainerId, sessionNumber: 1 })
  const saved = (await read(page, '/api/directory')).clients.find(c => c.id === client.id)
  expect(saved.purchases.map(p => [p.id, p.total_sessions, p.used, p.start_date, p.end_date])).toEqual(client.purchases.map(p => [p.id, p.total_sessions, p.used, p.start_date, p.end_date]))
}

test('Owner postponement UI preserves IDs, other bookings, purchased validity and credits after reload', async ({ page }, info) => {
  const { client, sessions } = await open(page, info, 'postpone')
  const stale = await preview(page)
  await expect(stale.getByRole('table')).toContainText(`${sessions[0].startsAt}–${sessions[0].endsAt}`)
  const review = await read(page, `/api/sessions/${sessions[0].id}/booking-review`)
  const changed = await post(page, `/api/sessions/${sessions[0].id}/booking`, { expected: review.expected, date: review.session.date, startsAt: review.session.startsAt, endsAt: '11:30', trainerId: review.session.trainerId })
  expect(changed.status()).toBe(200)
  const rejected = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith(`/api/sessions/${sessions[0].id}/postponement`))
  await stale.getByRole('button', { name: 'Confirm Postponement', exact: true }).click()
  expect((await rejected).status()).toBe(409)
  await expect(stale.getByRole('alert')).toBeVisible()
  expect((await read(page, `/api/sessions/${sessions[0].id}/booking-review`)).session).toMatchObject({ scheduleState: 'booked', endsAt: '11:30' })
  await stale.getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.reload()
  await confirm(page, await preview(page))
  await expect(page.getByText('Session postponed.', { exact: true })).toBeVisible()
  await assertOpen(page, client, sessions)
})

test('an autonomous assigned Trainer can release only its own current booking', async ({ page }, info) => {
  const { client, sessions } = await open(page, info, 'postponeauto', 'trainer')
  const dialog = await preview(page)
  await expect(dialog.getByText('Owner approval is required.', { exact: false })).toHaveCount(0)
  await confirm(page, dialog)
  await assertOpen(page, client, sessions)
})

test('supervised Trainer postponement persists a proposal and cancellation never releases the booking', async ({ page }, info) => {
  const { client, sessions } = await open(page, info, 'postponesupervised', 'trainer')
  const dialog = await preview(page)
  await expect(dialog).toContainText('Owner approval is required. The current booking stays unchanged until approved.')
  await confirm(page, dialog)
  await expect(page.getByText('Postponement requested. The booking stays unchanged until approved.', { exact: true })).toBeVisible()
  await page.reload()
  let saved = (await read(page, '/api/session-calendar')).sessions.filter(s => s.clientId === client.id).sort((a, b) => a.sessionNumber - b.sessionNumber)
  expect(saved).toEqual(sessions)
  const messages = await read(page, '/api/messages')
  const notice = messages.find(m => m.request?.kind === 'session_postpone' && m.request.session_id === sessions[0].id)
  expect(notice.request.status).toBe('pending')
  await page.getByRole('banner').getByRole('button', { name: 'Messages', exact: true }).click()
  await page.getByRole('button', { name: `Open ${notice.title}`, exact: true }).click()
  await page.getByRole('button', { name: 'Cancel Request', exact: true }).click()
  await page.getByRole('dialog', { name: 'Cancel this request?', exact: true }).getByRole('button', { name: 'Cancel Request', exact: true }).click()
  await expect(page.getByText(/Cancelled by/)).toBeVisible()
  await page.reload()
  saved = (await read(page, '/api/session-calendar')).sessions.filter(s => s.clientId === client.id).sort((a, b) => a.sessionNumber - b.sessionNumber)
  expect(saved).toEqual(sessions)
  expect((await read(page, '/api/messages')).find(m => m.id === notice.id).request.status).toBe('cancelled')
})

test('reopening an interrupted postponement reconciles its original key without another write', async ({ page }, info) => {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    window.postponementWrites = 0
    window.fetch = async (url, options) => {
      const response = await original(url, options)
      if (options?.method === 'POST' && /\/api\/sessions\/[^/]+\/postponement$/.test(String(url))) {
        window.postponementWrites += 1
        if (window.postponementWrites === 1 && response.ok) { await response.clone().text(); throw new TypeError('Lost committed postponement response') }
      }
      return response
    }
  })
  const { client, sessions } = await open(page, info, 'postponeloss')
  let dialog = await preview(page)
  await dialog.getByRole('button', { name: 'Confirm Postponement', exact: true }).click()
  await expect(dialog.getByRole('alert')).toBeVisible()
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  dialog = await preview(page)
  await confirm(page, dialog)
  await expect(page.getByText('Session postponed.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => window.postponementWrites)).toBe(1)
  await assertOpen(page, client, sessions)
})

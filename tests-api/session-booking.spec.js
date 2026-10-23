import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function open(page, info, purpose, role = 'owner') {
  await signIn(page, role, account(purpose, role))
  const directory = await read(page, '/api/directory')
  const client = directory.clients.find(c => c.name === `${info.project.name} ${purpose}`)
  const calendar = await read(page, '/api/session-calendar')
  const sessions = calendar.sessions.filter(s => s.clientId === client.id)
  if (purpose === 'bookingopen') sessions.sort((a, b) => Number(a.scheduleState === 'open') - Number(b.scheduleState === 'open'))
  expect(sessions).toHaveLength(2)
  await page.goto(`/#/sessions/${sessions[1].id}`)
  const panel = page.locator('.session-overview-panel')
  await expect(panel.getByRole('button', { name: purpose === 'bookingopen' ? 'Change ad-hoc date/time' : 'Edit', exact: true })).toBeEnabled()
  return { client, session: sessions[1], panel }
}

async function edit(page, panel, start, end) {
  await panel.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByLabel('Session start time', { exact: true }).fill(start)
  await page.getByLabel('Session end time', { exact: true }).fill(end)
}
async function save(page, panel, label = 'Save') {
  await panel.getByRole('button', { name: label, exact: true }).click()
  await page.getByRole('dialog', { name: 'Save session details?', exact: true }).getByRole('button', { name: 'Save Changes', exact: true }).click()
}

test('Owner booking UI persists to PostgreSQL through reload and fresh Admin login', async ({ page, browser }, info) => {
  const { client, session, panel } = await open(page, info, 'booking')
  await edit(page, panel, '14:00', '15:00')
  await save(page, panel)
  await expect(panel).toContainText('14:00–15:00')
  await page.reload()
  await expect(panel).toContainText('14:00–15:00')
  const context = await freshContext(browser, page)
  try {
    const fresh = await context.newPage()
    await signIn(fresh, 'admin', account('booking', 'admin'))
    await fresh.goto(`/#/sessions/${session.id}`)
    await expect(fresh.locator('.session-overview-panel')).toContainText('14:00–15:00')
    const saved = (await read(fresh, '/api/session-calendar')).sessions.find(s => s.id === session.id)
    expect(saved).toMatchObject({ clientId: client.id, startsAt: '14:00', endsAt: '15:00', trainerId: session.trainerId })
    const directory = await read(fresh, '/api/directory')
    expect(directory.clients.find(c => c.id === client.id).purchases[0].used).toBe(0)
  } finally { await context.close() }
})

test('Admin booking UI rejects stale review and Trainer cannot mutate foreign bookings', async ({ page, browser }, info) => {
  const { session, panel } = await open(page, info, 'bookingconflict', 'admin')
  await edit(page, panel, '14:00', '15:00')
  const review = await read(page, `/api/sessions/${session.id}/booking-review`)
  const response = await post(page, `/api/sessions/${session.id}/booking`, { expected: review.expected, date: review.session.date, startsAt: '16:00', endsAt: '17:00', trainerId: session.trainerId })
  expect(response.status()).toBe(200)
  await save(page, panel)
  await expect(page.getByRole('alert')).toBeVisible()
  expect((await read(page, `/api/sessions/${session.id}/booking-review`)).session.startsAt).toBe('16:00')
  const context = await freshContext(browser, page)
  try {
    const trainer = await context.newPage()
    await signIn(trainer, 'trainer')
    expect((await trainer.request.get(`/api/sessions/${session.id}/details`)).status()).toBe(404)
    expect((await trainer.request.get(`/api/sessions/${session.id}/booking-review`)).status()).toBe(403)
    expect((await post(trainer, `/api/sessions/${session.id}/booking`, { expected: review.expected, date: review.session.date, startsAt: '18:00', endsAt: '19:00', trainerId: session.trainerId })).status()).toBe(403)
  } finally { await context.close() }
})

test('lost booking response reconciles the committed original without a second write', async ({ page }, info) => {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    window.bookingWriteCount = 0
    window.fetch = async (url, options) => {
      const response = await original(url, options)
      if (options?.method === 'POST' && /\/api\/sessions\/[^/]+\/booking$/.test(String(url))) {
        window.bookingWriteCount += 1
        if (window.bookingWriteCount === 1 && response.ok) { await response.clone().text(); throw new TypeError('Simulated lost committed response') }
      }
      return response
    }
  })
  const { session, panel } = await open(page, info, 'bookingloss')
  await edit(page, panel, '14:00', '15:00')
  await save(page, panel)
  await expect(panel.getByRole('button', { name: 'Check original save', exact: true })).toBeVisible()
  await expect(page.getByLabel('Session start time', { exact: true })).toBeDisabled()
  expect((await read(page, `/api/sessions/${session.id}/booking-review`)).session.startsAt).toBe('14:00')
  await save(page, panel, 'Check original save')
  await expect(panel).toContainText('14:00–15:00')
  expect(await page.evaluate(() => window.bookingWriteCount)).toBe(1)
  await page.reload()
  await expect(panel).toContainText('14:00–15:00')
})

test('an Open session receives a durable date and chronological position through the UI', async ({ page }, info) => {
  const { session, panel } = await open(page, info, 'bookingopen')
  expect(session.scheduleState).toBe('open')
  const directory = await read(page, '/api/directory')
  const date = new Date(`${directory.businessDate}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + 3)
  const nextDate = date.toISOString().slice(0, 10)
  await panel.getByRole('button', { name: 'Change ad-hoc date/time', exact: true }).click()
  await page.getByLabel('Session date', { exact: true }).fill(nextDate)
  await page.getByLabel('Session start time', { exact: true }).fill('14:00')
  await page.getByLabel('Session end time', { exact: true }).fill('15:00')
  await save(page, panel)
  await expect(panel).toContainText('14:00–15:00')
  await page.reload()
  await expect(panel).toContainText('14:00–15:00')
  const reviewed = await read(page, `/api/sessions/${session.id}/booking-review`)
  expect(reviewed.session).toMatchObject({ id: session.id, scheduleState: 'booked', date: nextDate, sessionNumber: 1, slotId: null })
})

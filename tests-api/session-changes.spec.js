import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function open(page, info, purpose) {
  await signIn(page, 'trainer', `${info.project.name}-${purpose}@example.test`)
  const directory = await read(page, '/api/directory')
  expect(directory.clients.map(c => c.name)).toEqual([`${info.project.name} ${purpose}`])
  const client = directory.clients[0]
  const sessions = (await read(page, '/api/session-calendar')).sessions.sort((a, b) => a.sessionNumber - b.sessionNumber)
  expect(sessions).toHaveLength(2)
  expect(sessions.every(s => s.clientId === client.id && s.readAccess === 'assigned')).toBe(true)
  await page.goto(`/#/sessions/${sessions[0].id}`)
  await expect(page.getByRole('button', { name: 'Request Time Change', exact: true })).toBeEnabled()
  return { client, sessions }
}
async function edit(page, kind, replacement) {
  const title = kind === 'time' ? 'Request Time Change' : 'Request Trainer Change'
  await page.getByRole('button', { name: title, exact: true }).click()
  const dialog = page.getByRole('dialog', { name: title, exact: true })
  if (kind === 'time') {
    await dialog.getByLabel('Requested start time').fill('12:00')
    await dialog.getByLabel('Requested end time').fill('13:00')
  } else {
    await dialog.getByLabel('Requested replacement trainer').click()
    await page.getByRole('listbox', { name: 'Requested replacement trainer', exact: true }).getByRole('option', { name: replacement, exact: true }).click()
  }
  return dialog
}
async function submit(page, dialog, kind) {
  await dialog.getByRole('button', { name: 'Review Request', exact: true }).click()
  await page.getByRole('dialog', { name: kind === 'time' ? 'Submit time-change request?' : 'Submit trainer-change request?', exact: true }).getByRole('button', { name: 'Submit Request', exact: true }).click()
}
async function freshTrainer(browser, page, info, purpose, replacement = false) {
  const context = await freshContext(browser, page), next = await context.newPage()
  await signIn(next, 'trainer', `${info.project.name}-${purpose}${replacement ? '-replacement' : ''}@example.test`)
  return { context, page: next }
}

for (const [purpose, kind] of [['changetime', 'time'], ['changetrainer', 'trainer']]) {
  test(`autonomous ${kind} UI change persists and fresh Trainer scopes exclude foreign bookings`, async ({ page, browser }, info) => {
    const before = await open(page, info, purpose)
    await submit(page, await edit(page, kind, `${info.project.name} ${purpose} Replacement`), kind)
    await expect(page.getByText('Session change saved.', { exact: true })).toBeVisible()
    await page.reload()
    const fresh = await freshTrainer(browser, page, info, purpose, kind === 'trainer')
    const saved = (await read(fresh.page, '/api/session-calendar')).sessions
    expect(saved.every(s => s.clientId === before.client.id && s.readAccess === 'assigned')).toBe(true)
    const changed = saved.find(s => s.id === before.sessions[0].id)
    expect(changed).toBeTruthy()
    if (kind === 'time') expect(changed).toMatchObject({ startsAt: '12:00', endsAt: '13:00', trainerId: before.sessions[0].trainerId })
    else {
      const attribution = await read(fresh.page, `/api/sessions/${changed.id}/attribution`)
      expect(attribution.originalState).toBe('captured')
      expect(attribution.original.id).toBe(before.sessions[0].trainerId)
      expect(attribution.assigned.id).toBe(changed.trainerId)
      expect(attribution.performedBy).toBeNull()
      expect(attribution.history).toHaveLength(1)
      expect(attribution.history[0]).toMatchObject({ oldTrainerId: before.sessions[0].trainerId, newTrainerId: changed.trainerId, requestId: null })
      expect((await read(page, `/api/sessions/${changed.id}/attribution`))).toEqual(attribution)
      expect(changed.trainerId).not.toBe(before.sessions[0].trainerId)
      expect(saved).toHaveLength(1)
      const original = (await read(page, '/api/session-calendar')).sessions
      expect(original.map(s => s.id).sort()).toEqual(before.sessions.map(s => s.id).sort())
      expect(original.find(s => s.id === before.sessions[0].id)).toMatchObject({ trainerId: changed.trainerId, readAccess: 'historical' })
      expect(original.find(s => s.id === before.sessions[1].id).readAccess).toBe('assigned')
      expect((await page.request.get(`/api/sessions/${before.sessions[0].id}/change-review?kind=trainer`)).status()).toBe(404)
      expect((await post(page, `/api/sessions/${before.sessions[0].id}/trainer-change`, { expected: '0'.repeat(64), trainerId: before.sessions[0].trainerId })).status()).toBe(404)
    }
    const owner = await freshContext(browser, page), staff = await owner.newPage()
    await signIn(staff, 'owner', account(purpose))
    const all = (await read(staff, '/api/session-calendar')).sessions
    const foreign = all.find(s => s.clientId !== before.client.id)
    expect(foreign).toBeTruthy()
    expect((await fresh.page.request.get(`/api/sessions/${foreign.id}/attribution`)).status()).toBe(404)
    expect((await fresh.page.request.get(`/api/sessions/${foreign.id}/change-review?kind=${kind}`)).status()).toBe(404)
    const current = (await read(staff, '/api/directory')).clients.find(c => c.id === before.client.id)
    expect(current.purchases.map(p => [p.id, p.total_sessions, p.used, p.start_date, p.end_date])).toEqual(before.client.purchases.map(p => [p.id, p.total_sessions, p.used, p.start_date, p.end_date]))
    await fresh.context.close(); await owner.close()
  })
}

for (const [purpose, kind] of [['changetimesupervised', 'time'], ['changetrainersupervised', 'trainer']]) {
  test(`supervised ${kind} UI proposal leaves bookings intact until Owner approval`, async ({ page, browser }, info) => {
    const before = await open(page, info, purpose)
    await submit(page, await edit(page, kind, `${info.project.name} ${purpose} Replacement`), kind)
    await expect(page.getByText('Change requested. The booking stays unchanged until approved.', { exact: true })).toBeVisible()
    await page.reload()
    expect((await read(page, '/api/session-calendar')).sessions.sort((a, b) => a.sessionNumber - b.sessionNumber)).toEqual(before.sessions)
    const notice = (await read(page, '/api/messages')).find(m => m.request?.kind === `session_${kind}` && m.request.session_id === before.sessions[0].id)
    expect(notice.request.status).toBe('pending')
    const owner = await freshContext(browser, page), staff = await owner.newPage()
    await signIn(staff, 'owner', account(purpose))
    const allBefore = (await read(staff, '/api/session-calendar')).sessions
    await staff.getByRole('banner').getByRole('button', { name: 'Messages', exact: true }).click()
    await staff.getByRole('button', { name: `Open ${notice.title}`, exact: true }).click()
    await staff.getByRole('button', { name: 'Approve Request', exact: true }).click()
    await staff.getByRole('dialog', { name: 'Approve request?', exact: true }).getByRole('button', { name: 'Approve Request', exact: true }).click()
    await expect(staff.getByText('Request approved.', { exact: true })).toBeVisible()
    const allAfter = (await read(staff, '/api/session-calendar')).sessions
    expect(allAfter.filter(s => s.clientId !== before.client.id)).toEqual(allBefore.filter(s => s.clientId !== before.client.id))
    const fresh = await freshTrainer(browser, page, info, purpose, kind === 'trainer')
    const saved = (await read(fresh.page, '/api/session-calendar')).sessions
    expect(saved.every(s => s.clientId === before.client.id && s.readAccess === 'assigned')).toBe(true)
    expect(saved.find(s => s.id === before.sessions[0].id)).toMatchObject(kind === 'time' ? { startsAt: '12:00', endsAt: '13:00' } : { date: before.sessions[0].date, startsAt: before.sessions[0].startsAt })
    if (kind === 'trainer') {
      const attribution = await read(fresh.page, `/api/sessions/${before.sessions[0].id}/attribution`)
      expect(attribution.original.id).toBe(before.sessions[0].trainerId)
      expect(attribution.history).toHaveLength(1)
      expect(attribution.history[0].requestId).toBe(notice.request.id)
      expect(attribution.history[0].requestedBy.id).not.toBe(attribution.history[0].recordedBy.id)
      expect(attribution.history[0].newTrainerId).toBe(attribution.assigned.id)
    }
    await fresh.context.close(); await owner.close()
  })
}

test('stale Trainer review cannot overwrite an Owner booking change', async ({ page, browser }, info) => {
  const before = await open(page, info, 'changestale')
  const dialog = await edit(page, 'time')
  const owner = await freshContext(browser, page), staff = await owner.newPage()
  await signIn(staff, 'owner', account('changestale'))
  const reviewed = await read(staff, `/api/sessions/${before.sessions[0].id}/booking-review`)
  const response = await post(staff, `/api/sessions/${reviewed.id}/booking`, { expected: reviewed.expected, date: reviewed.session.date, startsAt: '14:00', endsAt: '15:00', trainerId: reviewed.session.trainerId })
  expect(response.status()).toBe(200)
  await submit(page, dialog, 'time')
  await expect(page.getByRole('dialog', { name: 'Request Time Change', exact: true }).getByRole('alert')).toBeVisible()
  await page.reload()
  expect((await read(page, '/api/session-calendar')).sessions.find(s => s.id === reviewed.id)).toMatchObject({ startsAt: '14:00', endsAt: '15:00' })
  await owner.close()
})

test('lost committed reassignment response keeps original receipt recoverable without another write', async ({ page, browser }, info) => {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    window.sessionChangeWrites = 0
    window.fetch = async (url, options) => {
      const response = await original(url, options)
      if (options?.method === 'POST' && /\/api\/sessions\/[^/]+\/trainer-change$/.test(String(url))) {
        window.sessionChangeWrites++
        window.originalSessionChangeKey = options.headers['Idempotency-Key']
        if (window.sessionChangeWrites === 1 && response.ok) { await response.clone().text(); throw new TypeError('Lost committed reassignment response') }
      }
      return response
    }
  })
  const before = await open(page, info, 'changeloss')
  await submit(page, await edit(page, 'trainer', `${info.project.name} changeloss Replacement`), 'trainer')
  const dialog = page.getByRole('dialog', { name: 'Request Trainer Change', exact: true })
  await expect(dialog.getByRole('alert')).toBeVisible()
  await expect(dialog.getByLabel('Requested replacement trainer')).toBeDisabled()
  // A normal focus refresh can observe the new assignment before the lost response is reconciled.
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Session change', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Check original change', exact: true }).click()
  await expect(page.getByText('Original session change confirmed.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => window.sessionChangeWrites)).toBe(1)
  const key = await page.evaluate(() => window.originalSessionChangeKey)
  expect((await read(page, `/api/session-changes/${key}`)).session.id).toBe(before.sessions[0].id)
  const fresh = await freshTrainer(browser, page, info, 'changeloss', true)
  expect((await read(fresh.page, '/api/session-calendar')).sessions.map(s => s.id)).toEqual([before.sessions[0].id])
  expect((await fresh.page.request.get(`/api/session-changes/${key}`)).status()).toBe(404)
  await fresh.context.close()
})

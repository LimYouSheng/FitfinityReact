import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

async function open(page, info, purpose, role = 'trainer') {
  await signIn(page, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose, role))
  const directory = await read(page, '/api/directory')
  const client = directory.clients.find(c => c.name === `${info.project.name} ${purpose}`)
  expect(client).toBeTruthy()
  const all = (await read(page, '/api/session-calendar')).sessions
  if (role === 'trainer') expect(all).toHaveLength(2)
  else expect(all.some(s => s.clientId !== client.id)).toBe(true)
  const session = all.find(s => s.clientId === client.id && s.sessionNumber === 1)
  await page.goto(`/#/sessions/${session.id}`)
  await page.getByRole('button', { name: 'Client Signature', exact: true }).click()
  await page.getByRole('button', { name: 'Record late / no-show instead' }).click()
  await page.getByLabel('Acknowledgement note').fill('Client absent; retained completion evidence.')
  return { client, session }
}
async function submit(page) {
  await page.getByRole('button', { name: 'Review Completion', exact: true }).click()
  await page.getByRole('dialog', { name: 'Complete this session?' }).getByRole('button', { name: 'Complete Session', exact: true }).click()
}
async function draw(page) {
  const pad = page.getByRole('img', { name: 'Draw client signature' })
  await pad.scrollIntoViewIfNeeded()
  const box = await pad.boundingBox()
  await page.mouse.move(box.x + 20, box.y + 20)
  await page.mouse.down()
  await page.mouse.move(box.x + 60, box.y + 50, { steps: 4 })
  await page.mouse.move(box.x + 100, box.y + 25, { steps: 4 })
  await page.mouse.up()
}
for (const [purpose, role] of [['ack', 'trainer'], ['ackadmin', 'admin']]) {
  test(`${role} completes through UI and corrects no-show to permanent signature with one credit`, async ({ page, browser }, info) => {
    const { session } = await open(page, info, purpose, role)
    await submit(page)
    await expect(page.getByText('Session acknowledgement saved.', { exact: true })).toBeVisible()
    await page.reload()
    await page.getByRole('button', { name: 'Correct to Client Signature' }).click()
    await draw(page)
    await submit(page)
    await expect(page.getByRole('button', { name: 'View Client Signature' })).toBeVisible()
    const context = await freshContext(browser, page), next = await context.newPage()
    await signIn(next, role, role === 'trainer' ? `${info.project.name}-${purpose}@example.test` : account(purpose, role))
    const after = await read(next, `/api/sessions/${session.id}/details`)
    expect(after.session.status).toBe('completed')
    expect(after.purchase.used).toBe(1)
    expect(after.acknowledgementHistory.map(a => a.method)).toEqual(['late_no_show', 'signature'])
    expect(after.acknowledgementHistory[1].signature[0].length).toBeGreaterThan(2)
    expect(after.whatsappOpenCount).toBe(0)
    await next.goto(`/#/sessions/${session.id}`)
    await expect(next.getByRole('button', { name: 'View Client Signature' })).toBeVisible()
    await context.close()
  })
}

test('stale completion cannot debit twice and foreign records stay denied', async ({ page, browser }, info) => {
  const { client, session } = await open(page, info, 'ackstale')
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account('ackstale'))
  const viewed = await read(staff, `/api/sessions/${session.id}/acknowledgement-review`)
  expect((await post(staff, `/api/sessions/${session.id}/acknowledgement`, { expected: viewed.expected, method: 'late_no_show' })).ok()).toBe(true)
  const rejected = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith(`/api/sessions/${session.id}/acknowledgement`))
  await submit(page)
  expect((await rejected).status()).toBe(409)
  await expect(page.getByRole('dialog', { name: 'Trainer late / no-show', exact: true }).getByRole('alert').filter({ hasText: /changed|reload/i })).toBeVisible()
  await expect(page.getByLabel('Acknowledgement note')).toHaveValue('Client absent; retained completion evidence.')
  expect((await read(staff, `/api/sessions/${session.id}/details`)).purchase.used).toBe(1)
  const foreign = (await read(staff, '/api/session-calendar')).sessions.find(s => s.clientId !== client.id)
  expect(foreign).toBeTruthy()
  expect((await page.request.get(`/api/sessions/${foreign.id}/acknowledgement-review`)).status()).toBe(404)
  expect((await post(page, `/api/sessions/${foreign.id}/acknowledgement`, { expected: viewed.expected, method: 'late_no_show' })).status()).toBe(404)
  await context.close()
})

test('lost committed acknowledgement freezes intent and recovers one private receipt', async ({ page, browser }, info) => {
  await page.addInitScript(() => {
    const fetch = window.fetch.bind(window)
    window.ackWrites = 0
    window.fetch = async (url, options) => {
      const response = await fetch(url, options)
      if (options?.method === 'POST' && /\/api\/sessions\/[^/]+\/acknowledgement$/.test(String(url))) {
        window.ackWrites++
        window.ackKey = options.headers['Idempotency-Key']
        if (window.ackWrites === 1 && response.ok) { await response.clone().text(); throw new TypeError('Lost committed acknowledgement') }
      }
      return response
    }
  })
  const { session } = await open(page, info, 'ackloss')
  await submit(page)
  await expect(page.getByLabel('Acknowledgement note')).toBeDisabled()
  await expect(page.getByRole('dialog', { name: 'Trainer late / no-show' }).getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.getByRole('button', { name: 'Check original acknowledgement', exact: true }).click()
  await expect(page.getByText('Original session acknowledgement confirmed.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => window.ackWrites)).toBe(1)
  const key = await page.evaluate(() => window.ackKey)
  expect((await read(page, `/api/session-acknowledgements/${key}`)).used).toBe(1)
  const context = await freshContext(browser, page), staff = await context.newPage()
  await signIn(staff, 'owner', account('ackloss'))
  expect((await staff.request.get(`/api/session-acknowledgements/${key}`)).status()).toBe(404)
  const after = await read(staff, `/api/sessions/${session.id}/details`)
  expect(after.purchase.used).toBe(1)
  expect(after.acknowledgementHistory).toHaveLength(1)
  await context.close()
})


test('another-tab logout retires the private signature confirmation without completing or debiting', async ({ page, browser }, info) => {
  await signIn(page, 'owner', account('acklogout'))
  const directory = await read(page, '/api/directory')
  const client = directory.clients.find(row => row.name === `${info.project.name} acklogout`)
  const sessions = (await read(page, '/api/session-calendar')).sessions
  const session = sessions.find(row => row.clientId === client.id && row.sessionNumber === 1)
  const foreign = sessions.find(row => row.clientId !== client.id)
  expect(foreign).toBeTruthy()
  const before = await read(page, `/api/sessions/${session.id}/details`)
  const foreignBefore = await read(page, `/api/sessions/${foreign.id}/details`)
  const writes = []
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/acknowledgement')) writes.push(request.url()) })
  await page.goto(`/#/sessions/${session.id}`)
  await page.getByRole('button', { name: 'Client Signature', exact: true }).click()
  await draw(page)
  await page.getByRole('button', { name: 'Review Completion', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Complete this session?', exact: true })).toBeVisible()
  await expect(page.getByRole('img', { name: 'Review client signature' })).toBeVisible()
  const otherTab = await page.context().newPage()
  await otherTab.goto('/#/account')
  await otherTab.getByRole('button', { name: 'Sign Out', exact: true }).click()
  await expect(otherTab.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog', { name: 'Complete this session?', exact: true })).toHaveCount(0)
  await expect(page.getByRole('img', { name: 'Review client signature' })).toHaveCount(0)
  expect((await page.request.get(`/api/sessions/${session.id}/details`)).status()).toBe(401)
  expect(writes).toEqual([])
  await otherTab.close()
  const context = await freshContext(browser, page)
  try {
    const next = await context.newPage()
    await signIn(next, 'owner', account('acklogout'))
    const after = await read(next, `/api/sessions/${session.id}/details`)
    expect(after.session.status).toBe(before.session.status)
    expect(after.purchase.used).toBe(before.purchase.used)
    expect(after.acknowledgementHistory).toEqual(before.acknowledgementHistory)
    expect(await read(next, `/api/sessions/${foreign.id}/details`)).toEqual(foreignBefore)
    await next.goto(`/#/sessions/${session.id}`)
    await next.getByRole('button', { name: 'Client Signature', exact: true }).click()
    await draw(next)
    await submit(next)
    await expect(next.getByRole('button', { name: 'View Client Signature' })).toBeVisible()
    await next.reload()
    const saved = await read(next, `/api/sessions/${session.id}/details`)
    expect(saved.purchase.used).toBe(before.purchase.used + 1)
    expect(saved.acknowledgementHistory).toHaveLength(1)
  } finally { await context.close() }
})

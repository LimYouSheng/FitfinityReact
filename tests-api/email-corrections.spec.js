import { fetchRoute, test, expect, signIn, read, post, account, freshContext, confirm } from './fixtures.js'

async function openTrainer(page, info, scope, role = 'owner') {
  await signIn(page, role, account(scope, role))
  const trainer = (await read(page, '/api/directory')).trainers.find(item => item.name === `${info.project.name} ${scope} Trainer`)
  expect(trainer).toBeTruthy()
  await page.goto(`/#/trainers/${trainer.id}`)
  return trainer
}

async function requestAddress(page, trainer, address, correction = false) {
  await page.getByRole('button', { name: correction ? 'Correct Pending Email' : 'Change Login Email', exact: true }).click()
  await page.getByLabel('New trainer login email', { exact: true }).fill(address)
  const response = page.waitForResponse(item => item.url().endsWith(`/api/trainers/${trainer.id}/email-change`) && item.request().method() === 'POST')
  await confirm(page, 'Request Verification')
  const saved = await response
  expect(saved.status()).toBe(200)
  await expect(page.getByText(`Awaiting the trainer’s verification of ${address}. The current email is still active.`, { exact: true })).toBeVisible()
  return { change: await saved.json(), key: saved.request().headers()['idempotency-key'], body: saved.request().postDataJSON() }
}

for (const role of ['owner', 'admin']) test(`${role} corrects reviewed pending email and only Trainer verification switches login`, async ({ page, browser }, info) => {
  const scope = role === 'owner' ? 'email' : 'emailadmin'
  const trainer = await openTrainer(page, info, scope, role)
  const first = `${info.project.name}-${scope}-wrong@example.test`, replacement = `${info.project.name}-${scope}-verified@example.test`
  const original = await requestAddress(page, trainer, first)
  await page.reload()
  const corrected = await requestAddress(page, trainer, replacement, true)
  expect(corrected.body.supersedes).toBe(original.change.id)
  expect((await read(page, '/api/directory')).trainers.find(item => item.id === trainer.id).email).toBe(trainer.email)
  expect((await post(page, `/auth/email-change/${corrected.change.id}/send`, {})).status()).toBe(404)
  const context = await freshContext(browser, page)
  try {
    const holder = await context.newPage()
    await signIn(holder, 'trainer', trainer.email)
    expect((await post(holder, `/api/trainers/${trainer.id}/email-change`, corrected.body)).status()).toBe(403)
    expect((await holder.request.get(`/api/trainer-email-requests/${corrected.key}`)).status()).toBe(403)
    expect((await post(holder, `/auth/email-change/${original.change.id}/send`, {})).status()).toBe(409)
    await holder.goto('/#/account')
    await expect(holder.getByRole('region', { name: 'Email verification' })).toContainText(replacement)
    await holder.getByRole('button', { name: 'Send Verification Code', exact: true }).click()
    await holder.getByLabel('Email verification code', { exact: true }).fill('100001')
    await holder.getByRole('button', { name: 'Verify New Email', exact: true }).click()
    await expect(holder.getByRole('button', { name: 'Sign In', exact: true })).toBeVisible()
  } finally { await context.close() }
  const fresh = await freshContext(browser, page)
  try {
    const verified = await fresh.newPage()
    await signIn(verified, 'trainer', replacement)
    expect((await read(verified, '/auth/email-change')).change).toBeNull()
    const record = (await read(page, '/api/directory')).trainers.find(item => item.id === trainer.id)
    expect(record.email).toBe(replacement)
    expect((await read(page, `/api/trainer-email-requests/${original.key}`)).state).toBe('superseded')
    expect((await read(page, `/api/trainer-email-requests/${corrected.key}`)).state).toBe('completed')
  } finally { await fresh.close() }
})

test('stale email correction and foreign receipts cannot replace the current request', async ({ page, browser }, info) => {
  const trainer = await openTrainer(page, info, 'emailstale')
  const original = await requestAddress(page, trainer, `${info.project.name}-emailstale-first@example.test`)
  await page.getByRole('button', { name: 'Correct Pending Email', exact: true }).click()
  await page.getByLabel('New trainer login email', { exact: true }).fill(`${info.project.name}-emailstale-reviewed@example.test`)
  await page.getByRole('button', { name: 'Request Verification', exact: true }).click()
  const context = await freshContext(browser, page)
  try {
    const other = await context.newPage()
    await signIn(other, 'admin', account('emailstale', 'admin'))
    expect((await other.request.get(`/api/trainer-email-requests/${original.key}`)).status()).toBe(404)
    const address = `${info.project.name}-emailstale-winning@example.test`
    const competing = await post(other, `/api/trainers/${trainer.id}/email-change`, { expectedVersion: trainer.version, supersedes: original.change.id, email: address })
    expect(competing.status()).toBe(200)
    await page.getByRole('dialog').getByRole('button', { name: 'Request Verification', exact: true }).click()
    await expect(page.getByRole('alert').first()).toContainText('Review the pending verification')
    expect((await read(page, `/api/trainers/${trainer.id}/email-change`)).change.email).toBe(address)
    await page.getByRole('button', { name: 'Cancel', exact: true }).click()
    await page.reload()
    await expect(page.getByText(`Awaiting the trainer’s verification of ${address}. The current email is still active.`, { exact: true })).toBeVisible()
    expect((await read(page, '/api/directory')).trainers.find(item => item.id === trainer.id).email).toBe(trainer.email)
  } finally { await context.close() }
})

test('lost correction response recovers one original request and survives fresh Manager login', async ({ page, browser }, info) => {
  const trainer = await openTrainer(page, info, 'emailloss')
  await requestAddress(page, trainer, `${info.project.name}-emailloss-wrong@example.test`)
  const address = `${info.project.name}-emailloss-correct@example.test`
  let writes = 0, key
  const path = `**/api/trainers/${trainer.id}/email-change`
  await page.route(path, async route => {
    if (route.request().method() !== 'POST') return route.continue()
    writes++; key = route.request().headers()['idempotency-key']
    const response = await fetchRoute(route)
    expect(response.status()).toBe(200)
    await route.abort('failed')
  })
  await page.getByRole('button', { name: 'Correct Pending Email', exact: true }).click()
  await page.getByLabel('New trainer login email', { exact: true }).fill(address)
  await confirm(page, 'Request Verification')
  await expect(page.getByRole('button', { name: 'Check Original Request', exact: true })).toBeVisible()
  await expect(page.getByLabel('New trainer login email', { exact: true })).toBeDisabled()
  await page.unroute(path)
  await page.getByRole('button', { name: 'Check Original Request', exact: true }).click()
  await expect(page.getByText(`Awaiting the trainer’s verification of ${address}. The current email is still active.`, { exact: true })).toBeVisible()
  expect(writes).toBe(1)
  expect((await read(page, `/api/trainer-email-requests/${key}`)).email).toBe(address)
  const context = await freshContext(browser, page)
  try {
    const fresh = await context.newPage()
    await signIn(fresh, 'owner', account('emailloss'))
    await fresh.goto(`/#/trainers/${trainer.id}`)
    await expect(fresh.getByText(`Awaiting the trainer’s verification of ${address}. The current email is still active.`, { exact: true })).toBeVisible()
    expect((await read(fresh, '/api/directory')).trainers.find(item => item.id === trainer.id).email).toBe(trainer.email)
  } finally { await context.close() }
})

test('supervised email change recovers lost submission and requires Trainer verification after Owner approval', async ({ page, browser }, info) => {
  const scope = 'emailapproval'
  const trainer = await openTrainer(page, info, scope)
  const admin = (await read(page, '/api/staff/admins')).find(item => item.details.email === account(scope, 'admin'))
  expect(admin).toBeTruthy()
  const changed = await post(page, `/api/staff/admins/${admin.id}`, {
    expectedVersion: admin.version, operation: 'approvals', approvalNeeded: { ...admin.approvalNeeded, trainerDetails: true },
  })
  expect(changed.status()).toBe(200)
  const context = await freshContext(browser, page)
  const address = `${info.project.name}-emailapproval-reviewed@example.test`
  try {
    const manager = await context.newPage()
    await signIn(manager, 'admin', account(scope, 'admin'))
    await manager.goto(`/#/trainers/${trainer.id}`)
    let writes = 0, key
    const path = `**/api/trainers/${trainer.id}/email-change`
    await manager.route(path, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      writes++; key = route.request().headers()['idempotency-key']
      const response = await fetchRoute(route)
      expect(response.status()).toBe(202)
      await route.abort('failed')
    })
    await manager.getByRole('button', { name: 'Change Login Email', exact: true }).click()
    await manager.getByLabel('New trainer login email', { exact: true }).fill(address)
    await confirm(manager, 'Request Verification')
    await expect(manager.getByRole('button', { name: 'Check Original Request', exact: true })).toBeVisible()
    await manager.unroute(path)
    await manager.getByRole('button', { name: 'Check Original Request', exact: true }).click()
    await expect(manager.getByRole('status').filter({ hasText: 'Submitted for Owner approval.' })).toBeVisible()
    expect(writes).toBe(1)
    expect((await read(manager, `/api/trainers/${trainer.id}/email-change`)).change).toBeNull()
    expect((await read(manager, '/api/directory')).trainers.find(item => item.id === trainer.id).email).toBe(trainer.email)
    const requests = (await read(manager, '/api/admin-requests')).filter(item => item.operation === 'trainer.email')
    expect(requests).toHaveLength(1)
    await page.goto('/#/messages')
    const row = page.locator('.info-row').filter({ hasText: 'emailapproval admin' }).filter({ hasText: 'pending' })
    await row.getByRole('button', { name: 'Review', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Request verified Trainer email change', exact: true })).toBeVisible()
    await expect(page.getByText(address, { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Approve', exact: true }).click()
    await page.getByRole('dialog', { name: 'Approve?', exact: true }).getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(page.getByText('emailapproval admin · approved', { exact: true })).toBeVisible()
    await manager.reload()
    await expect(manager.getByText(`Awaiting the trainer’s verification of ${address}. The current email is still active.`, { exact: true })).toBeVisible()
    expect((await read(manager, `/api/trainer-email-requests/${key}`)).state).toBe('requested')
    const saved = (await read(manager, `/api/trainers/${trainer.id}/email-change`)).change
    expect((await post(manager, `/auth/email-change/${saved.id}/send`, {})).status()).toBe(404)
  } finally { await context.close() }
  const holderContext = await freshContext(browser, page)
  try {
    const holder = await holderContext.newPage()
    await signIn(holder, 'trainer', trainer.email)
    await holder.goto('/#/account')
    await expect(holder.getByRole('region', { name: 'Email verification' })).toContainText(address)
    await holder.getByRole('button', { name: 'Send Verification Code', exact: true }).click()
    await holder.getByLabel('Email verification code', { exact: true }).fill('100001')
    await holder.getByRole('button', { name: 'Verify New Email', exact: true }).click()
    await expect(holder.getByRole('button', { name: 'Sign In', exact: true })).toBeVisible()
    await signIn(holder, 'trainer', address)
    expect((await read(holder, '/auth/email-change')).change).toBeNull()
    expect((await read(page, '/api/directory')).trainers.find(item => item.id === trainer.id).email).toBe(address)
  } finally { await holderContext.close() }
})

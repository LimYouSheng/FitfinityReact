import { randomUUID } from 'node:crypto'
import { test, expect, signIn, read, post, account, freshContext } from './fixtures.js'

const workflows = [
  { kind: 'client', label: 'Client Information', heading: 'General Information', confirm: 'Save Changes' },
  { kind: 'trainer', label: 'Trainer Information', heading: 'General Information', confirm: 'Save Changes' },
  { kind: 'rates', label: 'Trainer Rates', heading: 'Training & Rates', confirm: 'Save Rates' },
  { kind: 'approvals', label: 'Approval Settings', heading: 'Owner Approval Needed', confirm: 'Save Controls' },
  { kind: 'package', label: 'Package Setup', heading: null, confirm: 'Save Package' },
]

for (const workflow of workflows) for (const committed of [true, false]) test(`${workflow.kind} Cancel recovers a ${committed ? 'committed' : 'uncommitted'} original save across navigation`, async ({ page, browser }, info) => {
  const { kind, label, heading } = workflow, scope = `recover-${kind}`
  await signIn(page, 'owner', account(scope))
  const directory = await read(page, '/api/directory')
  const client = directory.clients.find(row => row.name === `${info.project.name} ${scope}`)
  const foreign = directory.clients.find(row => row.id !== client.id)
  expect(foreign).toBeDefined()
  let record, path, panel
  if (kind === 'package') {
    const setup = await post(page, '/api/packages', { draft: { name: `Recovery ${randomUUID()}`, total: 12, status: 'active' } })
    expect(setup.status()).toBe(200)
    record = await setup.json()
    await page.goto(`/#/packages/${record.id}`)
    await page.reload()
    await page.getByRole('button', { name: 'Edit Package', exact: true }).click()
    await page.getByLabel('Package session count', { exact: true }).fill('18')
    panel = page.locator('.package-form')
    path = '/api/packages'
  } else {
    record = kind === 'client' ? client : directory.trainers.find(row => row.id === client.trainer_id)
    await page.goto(`/#/${kind === 'client' ? 'clients' : 'trainers'}/${record.id}`)
    panel = page.locator('.panel').filter({ has: page.getByRole('heading', { name: heading, exact: true }) })
    await panel.getByRole('button', { name: 'Edit', exact: true }).click()
    if (kind === 'client') await page.getByLabel('Client email', { exact: true }).fill(`recovered-${committed}@example.test`)
    if (kind === 'trainer') await page.getByLabel('Trainer qualifications', { exact: true }).fill(`Recovered qualification ${committed}`)
    if (kind === 'rates') await page.getByLabel('Peak rate', { exact: true }).fill(committed ? '65.43' : '66.54')
    if (kind === 'approvals') await panel.getByRole('checkbox', { name: 'Availability changes' }).setChecked(!record.approve_availability)
    path = `/api/${kind === 'client' ? 'clients' : 'trainers'}/${record.id}/${kind === 'rates' ? 'rates' : kind === 'approvals' ? 'approvals' : 'personal-details'}`
  }
  const writes = []
  await page.route(`**${path}`, async route => {
    if (route.request().method() !== 'POST') return route.continue()
    writes.push({ key: route.request().headers()['idempotency-key'], body: route.request().postData() })
    if (writes.length > 1) return route.continue()
    if (committed) expect((await route.fetch()).status()).toBe(200)
    await route.abort('failed')
  })
  await panel.getByRole('button', { name: kind === 'package' ? 'Save Package' : 'Save', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: workflow.confirm, exact: true }).click()
  await expect(panel.getByRole('button', { name: 'Cancel', exact: true })).toBeEnabled()
  await panel.getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.getByRole('button', { name: 'Home', exact: true }).click()
  await page.getByRole('button', { name: `Check Previous ${label} Save`, exact: true }).click()
  expect(writes).toHaveLength(1)
  if (!committed) {
    await page.getByRole('button', { name: `Retry Original ${label} Save`, exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Retry Original Save', exact: true }).click()
  }
  await expect(page.getByRole('button', { name: `Retry Original ${label} Save`, exact: true })).toHaveCount(0)
  expect(writes).toHaveLength(committed ? 1 : 2)
  if (!committed) expect(writes[1]).toEqual(writes[0])
  const fresh = await freshContext(browser, page)
  try {
    const next = await fresh.newPage()
    await signIn(next, 'owner', account(scope))
    const after = await read(next, '/api/directory')
    expect(after.clients.find(row => row.id === foreign.id)).toEqual(foreign)
    const saved = (kind === 'client' ? after.clients : kind === 'package' ? after.packages : after.trainers).find(row => row.id === record.id)
    expect(saved.version).toBe(record.version + 1)
    if (kind === 'client') expect(saved.people[0].email).toBe(`recovered-${committed}@example.test`)
    if (kind === 'trainer') expect(saved.qualifications).toBe(`Recovered qualification ${committed}`)
    if (kind === 'rates') expect(saved.peak_rate_cents).toBe(committed ? 6543 : 6654)
    if (kind === 'approvals') expect(saved.approve_availability).toBe(!record.approve_availability)
    if (kind === 'package') expect(saved.total_sessions).toBe(18)
  } finally { await fresh.close() }
})

test('an active package creation editor retains its original receipt for Save again', async ({ page }, info) => {
  await signIn(page, 'owner', account('recover-package'))
  const name = `One original creation ${info.project.name} ${randomUUID()}`
  await page.goto('/#/packages/new')
  await page.getByLabel('Package name', { exact: true }).fill(name)
  await page.getByLabel('Package session count', { exact: true }).fill('12')
  let writes = 0
  await page.route('**/api/packages', async route => {
    if (route.request().method() !== 'POST') return route.continue()
    writes++
    if (writes > 1) return route.continue()
    expect((await route.fetch()).status()).toBe(200)
    await route.abort('failed')
  })
  await page.getByRole('button', { name: 'Create Package', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Create Package', exact: true }).click()
  await expect(page.locator('.package-form')).toContainText('The response was interrupted')
  await expect(page.getByRole('button', { name: 'Create Package', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Create Package', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Create Package', exact: true }).click()
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
  expect(writes).toBe(1)
  expect((await read(page, '/api/directory')).packages.filter(row => row.name === name)).toHaveLength(1)
})

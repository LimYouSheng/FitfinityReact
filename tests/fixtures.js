import { test as base, expect } from '@playwright/test'
export { expect }
export const test = base.extend({
  demoSignedIn: [true, { option: true }],
  context: async ({ context, demoSignedIn }, use) => {
    if (demoSignedIn) await context.addInitScript(() => {
      const key='fitfinity-demo-session-v1'
      if (!localStorage.getItem(key)) localStorage.setItem(key,JSON.stringify({userId:'u-owner',expiresAt:Date.now()+100*365*86400000}))
    })
    await use(context)
  },
})
export async function drawClientSignature(page) {
  const pad=page.getByRole('img',{name:'Draw client signature'})
  await pad.scrollIntoViewIfNeeded()
  const rect=await pad.boundingBox()
  expect(rect?.width).toBeGreaterThan(0)
  await page.mouse.move(rect.x+rect.width*.1,rect.y+rect.height*.4)
  await page.mouse.down()
  await page.mouse.move(rect.x+rect.width*.3,rect.y+rect.height*.7,{steps:4})
  await page.mouse.move(rect.x+rect.width*.6,rect.y+rect.height*.2,{steps:4})
  await page.mouse.up()
}

export async function selectDemoIdentity(page, id) {
  await page.locator('.role-switcher select').selectOption(id)
  await expect(page.locator('.portal-shell')).toHaveAttribute('data-user-id', id)
  await expect(page.locator('.portal-shell')).toHaveAttribute('aria-busy', 'false')
}

// Stub only the OS share boundary; the application still renders its real PDF.
export async function mockPdfSharing(page, { supported = true, outcomes = [] } = {}) {
  await page.evaluate(({ supported, outcomes }) => {
    window.__pdfShares = []
    Object.defineProperty(navigator, 'canShare', { configurable: true, value: ({ files }) => supported && files?.length === 1 && files[0].type === 'application/pdf' })
    Object.defineProperty(navigator, 'share', { configurable: true, value: async data => {
      const active = navigator.userActivation.isActive
      const file = data.files[0], bytes = await file.arrayBuffer()
      const content = new TextDecoder('latin1').decode(bytes)
      const digest = await crypto.subtle.digest('SHA-256', bytes)
      window.__pdfShares.push({ name: file.name, type: file.type, size: file.size, active,
        keys: Object.keys(data), header: content.slice(0, 9), eof: content.endsWith('%%EOF\n'),
        images: (content.match(/\/Subtype \/Image/g) ?? []).length,
        sha256: Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('') })
      const outcome = outcomes.shift()
      if (outcome) throw new DOMException(outcome, outcome)
    } })
  }, { supported, outcomes })
}

// Existing workflow scenarios explicitly expand navigation before using its links.
// Sidebar-default scenarios do not call this helper.
export async function expandSidebarSections(page, { keepOpen = false } = {}) {
  await expect(page.locator('.portal-shell')).toHaveAttribute('aria-busy', 'false')
  const menu = page.getByRole('button', { name: 'Open navigation' })
  const openedHere = await menu.isVisible() && !(await page.locator('.sidebar').getAttribute('class')).includes('mobile-open')
  if (openedHere) await menu.click()
  const toggles = page.locator('.sidebar .nav-group-toggle')
  for (const toggle of await toggles.all()) {
    if (await toggle.getAttribute('aria-expanded') === 'false') await toggle.click()
  }
  if (openedHere && !keepOpen) {
    const sidebar = await page.locator('.sidebar').boundingBox()
    const viewport = page.viewportSize()
    await page.getByRole('button', { name: 'Close navigation', exact: true }).click({ position: { x: (sidebar.x + sidebar.width + viewport.width) / 2, y: viewport.height / 2 } })
    await expect(page.locator('.sidebar')).not.toHaveClass(/mobile-open/)
  }
}

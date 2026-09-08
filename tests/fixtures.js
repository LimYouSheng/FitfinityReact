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

// Existing workflow scenarios explicitly expand navigation before using its links.
// Sidebar-default scenarios do not call this helper.
export async function expandSidebarSections(page) {
  await expect(page.locator('.portal-shell')).toHaveAttribute('aria-busy', 'false')
  const toggles = page.locator('.sidebar .nav-group-toggle')
  for (const toggle of await toggles.all()) {
    if (await toggle.getAttribute('aria-expanded') === 'false') await toggle.click()
  }
}

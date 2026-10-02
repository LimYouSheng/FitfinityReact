// Exercise the DOM's touch path, including real event targets and a refresh
// between start/end. OS-reserved Safari edge gestures still need a device check.
async function touch(page, selector, type, origin, delta) {
  await page.locator(selector).evaluate((element, { type, origin, delta }) => {
    const point = { identifier: 7, clientX: origin.x + delta, clientY: origin.y, target: element }
    const event = new Event(type, { bubbles: true, cancelable: true })
    Object.assign(event, { touches: type === 'touchend' ? [] : [point], changedTouches: [point] })
    element.dispatchEvent(event)
  }, { type, origin, delta })
}
export async function swipe(page, selector = '.portal-main', during) {
  await page.evaluate(() => scrollTo(0, 0))
  // A finger moves in viewport coordinates. Page drag/scroll must not move the
  // synthetic finger or turn this horizontal gesture into a vertical one.
  const origin = await page.locator(selector).evaluate(element => {
    const rect = element.getBoundingClientRect()
    return { x: rect.left + 12, y: rect.top + 90 }
  })
  await touch(page, selector, 'touchstart', origin, 0)
  if (during) await during()
  await touch(page, selector, 'touchmove', origin, 155)
  await touch(page, selector, 'touchend', origin, 180)
}

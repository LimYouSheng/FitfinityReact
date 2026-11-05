import { expect } from './fixtures.js'

// A controlled payload: no external requests, credentials or persistent effects.
export const activeMarkup = '<svg xmlns="http://www.w3.org/2000/svg" onload="globalThis.mediaProbeExecuted=true"><script>globalThis.mediaProbeExecuted=true</script></svg>'

export async function assertInert(page) {
  expect(await page.evaluate(() => globalThis.mediaProbeExecuted === true)).toBe(false)
  await expect(page.locator('svg[onload], iframe, object, embed, [onerror]')).toHaveCount(0)
}

export async function proveActiveControl(browser) {
  const context = await browser.newContext()
  try {
    const page = await context.newPage()
    await page.setContent(activeMarkup)
    await expect.poll(() => page.evaluate(() => globalThis.mediaProbeExecuted)).toBe(true)
    // The same absence assertion must reject a real HTML interpretation.
    await expect(assertInert(page)).rejects.toThrow()
  } finally { await context.close() }
}

export async function settleMedia(locator) {
  await expect(locator).toHaveAttribute('src', /^blob:/)
  return locator.evaluate(element => new Promise(resolve => {
    const finish = event => {
      element.removeEventListener('load', finish)
      element.removeEventListener('error', finish)
      element.removeEventListener('loadedmetadata', finish)
      resolve(event?.type !== 'error' && (element instanceof HTMLImageElement
        ? element.naturalWidth > 0
        : !element.error && element.readyState > 0
          && Number.isFinite(element.duration) && element.duration > 0
          && element.videoWidth > 0 && element.videoHeight > 0))
    }
    element.addEventListener('load', finish, { once: true })
    element.addEventListener('error', finish, { once: true })
    element.addEventListener('loadedmetadata', finish, { once: true })
    if (element instanceof HTMLImageElement) {
      if (element.complete) finish()
    } else if (element instanceof HTMLVideoElement) {
      // Some decoders expose SVG as a zero-duration image track; metadata alone
      // does not establish a playable video. Require duration and dimensions above.
      // Reset any metadata belonging to the previous src and explicitly request
      // decoding: application previews intentionally use preload=none.
      element.preload = 'metadata'
      element.load()
    }
  }))
}


export function appendWebmVoid(clip, text) {
  const payload = Buffer.from(text)
  const header = Buffer.from([0xec, 0x40 | (payload.length >> 8), payload.length & 255])
  return Buffer.concat([clip, header, payload])
}

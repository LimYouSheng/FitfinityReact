import { createPortalServices } from './portalService.js'
import { createApiPortalAdapter } from './apiPortalAdapter.js'

export function createConfiguredPortalServices({ mode = 'demo', baseUrl = '', ...options } = {}) {
  let adapter
  const resolve = async () => {
    if (!adapter) {
      if (mode === 'api') adapter = createApiPortalAdapter({ baseUrl, ...options })
      else if (mode === 'demo') adapter = (await import('./mockPortalAdapter.js')).mockPortalAdapter
      else throw new Error('Unknown staff portal mode. Check the deployment configuration.')
    }
    return adapter
  }
  return createPortalServices(Object.fromEntries(['load', 'session', 'invoke', 'reset'].map(method => [method, async (...args) => (await resolve())[method](...args)])))
}

export const portalServices = createConfiguredPortalServices({ mode: import.meta.env.VITE_PORTAL_MODE ?? 'demo', baseUrl: import.meta.env.VITE_API_BASE_URL ?? '' })

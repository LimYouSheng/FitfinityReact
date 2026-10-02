import { browserReportService } from './reportService.js'
import { AUTH_CONTRACTS, PORTAL_CONTRACTS } from './portalContracts.js'

// Every public operation resolves asynchronously. Adapters validate requests before
// dispatch, supply their own authenticated identity, and preserve domain/API errors.
export function createPortalServices(adapter, reportService = browserReportService, sessionGeneration) {
  // A local concurrency guard, never a server identity or authorization input.
  const context = sessionGeneration === undefined ? [] : [{ expectedGeneration: sessionGeneration }]
  const services = { forSession: generation => createPortalServices(adapter, reportService, generation), reportService, load: async () => adapter.load(), reset: async () => adapter.reset() }
  for (const [service, operations] of Object.entries(PORTAL_CONTRACTS)) {
    services[service] = Object.fromEntries(Object.keys(operations).map(operation =>
      [operation, async (input = {}) => adapter.invoke({ service, operation, input }, ...context)]))
  }
  services.auth = Object.fromEntries(Object.keys(AUTH_CONTRACTS).map(operation =>
    [operation, async (input = {}) => adapter.session({ operation, input }, ...context)]))
  return services
}

import { browserReportService } from './reportService.js'

// Stable async contract. An API adapter supplies load/session/invoke/reset.
export const PORTAL_OPERATIONS = {
  "contentService": [
    "save"
  ],
  "clientService": [
    "getAll",
    "getById",
    "create",
    "renewPackage",
    "deactivatePackage",
    "deletePackageSessions",
    "update",
    "saveFixedWeeklySchedule",
    "reassignTrainer",
    "recordProgressReportAction",
    "progressReportHistory",
    "deactivate",
    "reactivate"
  ],
  "trainerService": [
    "create",
    "saveAvailability",
    "getAll",
    "getActive",
    "getById",
    "isSelectableForAvailability",
    "update",
    "updateAutonomy",
    "deactivate",
    "reactivate"
  ],
  "sessionService": [
    "loadVideo",
    "saveVideo",
    "removeVideo",
    "updateDetails",
    "requestTimeChange",
    "requestTrainerChange",
    "saveExercisePlan",
    "previousPlanFor",
    "copyPreviousPlan",
    "saveOutcome",
    "saveClientSummary",
    "markWhatsAppOpened",
    "acknowledge"
  ],
  "packageService": [
    "save"
  ],
  "exerciseLibraryService": [
    "loadMedia",
    "getAll",
    "save"
  ],
  "messageService": [
    "markRead",
    "markUnread"
  ],
  "requestService": [
    "resolve",
    "cancel"
  ],
  "remunerationService": [
    "list",
    "detail",
    "approve"
  ]
}

export function createPortalServices(adapter, reportService = browserReportService) {
  const services = { reportService, load: async () => adapter.load(), reset: async () => adapter.reset() }
  for (const [domain, implementation] of Object.entries(PORTAL_OPERATIONS)) {
    services[domain] = Object.fromEntries(implementation.map(method => [method, async (...args) => adapter.invoke(domain, method, args)]))
  }
  services.auth = Object.fromEntries(['signIn', 'signOut', 'switchDemoIdentity', 'changePassword'].map(method => [method, async (...args) => adapter.session(method, args)]))
  return services
}

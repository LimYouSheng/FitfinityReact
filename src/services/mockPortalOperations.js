import { staffService } from './staffService.js'
import { contentService } from './contentService.js'
import { clientService } from './clientService.js'
import { trainerService } from './trainerService.js'
import { sessionService } from './sessionService.js'
import { packageService } from './packageService.js'
import { exerciseLibraryService } from './exerciseLibraryService.js'
import { messageService } from './messageService.js'
import { requestService } from './requestService.js'
import { remunerationService } from './remunerationService.js'

// Handlers are the sole translation from named boundary requests to domain calls.
// Context is adapter-owned and never merged with caller input.
export const mockPortalOperations = {
  staffService: {
    createAdmin: ({ body, requestKey }, { actor }) => staffService.createAdmin(body, requestKey, actor),
  },
  contentService: {
    save: (input, { actor }) => contentService.save(input, actor),
  },
  clientService: {
    getAll: () => clientService.getAll(),
    getById: ({ id }) => clientService.getById(id),
    create: ({ draft }, { actor }) => clientService.create(draft, actor),
    renewPackage: ({ id, draft }, { actor }) => clientService.renewPackage(id, draft, actor),
    deactivatePackage: ({ id, options }, { actor }) => clientService.deactivatePackage(id, options, actor),
    deletePackageSessions: ({ id, options }, { actor }) => clientService.deletePackageSessions(id, options, actor),
    update: ({ id, patch }, { actor }) => clientService.update(id, patch, actor),
    saveAssessment: ({ id, assessment }, { actor }) => clientService.saveAssessment(id, assessment, actor),
    saveFixedWeeklySchedule: ({ id, slots }, { actor }) => clientService.saveFixedWeeklySchedule(id, slots, actor),
    reassignTrainer: ({ id, draft }, { actor }) => clientService.reassignTrainer(id, draft, actor),
    recordProgressReportAction: ({ id, action }, { actor }) => clientService.recordProgressReportAction(id, action, actor),
    progressReportHistory: ({ id, packageId }, { actor }) => clientService.progressReportHistory(id, actor, packageId),
    deactivate: ({ id }, { actor }) => clientService.deactivate(id, actor),
    reactivate: ({ id, dates, expected }, { actor }) => clientService.reactivate(id, actor, { dates, expected }),
  },
  trainerService: {
    create: ({ draft }, { actor }) => trainerService.create(draft, actor),
    saveAvailability: ({ id, blocks }, { actor }) => trainerService.saveAvailability(id, blocks, actor),
    getAll: () => trainerService.getAll(),
    getActive: () => trainerService.getActive(),
    getById: ({ id }) => trainerService.getById(id),
    isSelectableForAvailability: ({ trainer }) => trainerService.isSelectableForAvailability(trainer),
    update: ({ id, patch }, { actor }) => trainerService.update(id, patch, actor),
    updateAutonomy: ({ id, approvalNeeded }, { actor }) => trainerService.updateAutonomy(id, approvalNeeded, actor),
    deactivate: ({ id, replacements }, { actor }) => trainerService.deactivate(id, replacements, actor),
    reactivate: ({ id }, { actor }) => trainerService.reactivate(id, actor),
  },
  sessionService: {
    previewPostponement: ({ sessionId }, { actor }) => sessionService.previewPostponement(sessionId, actor),
    postpone: ({ sessionId, expected, requestKey }, { actor }) => sessionService.postpone(sessionId, expected, requestKey, actor),
    loadVideo: ({ sessionId, exerciseId }, { actor }) => sessionService.loadVideo(sessionId, exerciseId, actor),
    saveVideo: ({ sessionId, exerciseId, file, metadata }, { actor }) => sessionService.saveVideo(sessionId, exerciseId, file, metadata, actor),
    removeVideo: ({ sessionId, exerciseId }, { actor }) => sessionService.removeVideo(sessionId, exerciseId, actor),
    updateDetails: ({ sessionId, patch }, { actor }) => sessionService.updateDetails(sessionId, patch, actor),
    requestTimeChange: ({ sessionId, patch }, { actor }) => sessionService.requestTimeChange(sessionId, actor, patch),
    requestTrainerChange: ({ sessionId, replacementTrainerId }, { actor }) => sessionService.requestTrainerChange(sessionId, actor, replacementTrainerId),
    saveExercisePlan: ({ sessionId, items }, { actor }) => sessionService.saveExercisePlan(sessionId, items, actor),
    previousPlanFor: ({ sessionId }, { actor }) => sessionService.previousPlanFor(sessionId, actor),
    copyPreviousPlan: ({ sessionId }, { actor }) => sessionService.copyPreviousPlan(sessionId, actor),
    saveOutcome: ({ sessionId, outcome }, { actor }) => sessionService.saveOutcome(sessionId, outcome, actor),
    saveClientSummary: ({ sessionId, summary }, { actor }) => sessionService.saveClientSummary(sessionId, summary, actor),
    markWhatsAppOpened: ({ sessionId }, { actor }) => sessionService.markWhatsAppOpened(sessionId, actor),
    acknowledge: ({ sessionId, acknowledgement }, { actor }) => sessionService.acknowledge(sessionId, acknowledgement, actor),
  },
  packageService: {
    save: (input, { actor }) => packageService.save(input, actor),
  },
  exerciseLibraryService: {
    loadMedia: ({ id }) => exerciseLibraryService.loadMedia(id),
    getAll: (_input, { actor }) => exerciseLibraryService.getAll(actor),
    save: (input, { actor }) => exerciseLibraryService.save(input, actor),
  },
  messageService: {
    undo: ({ id }, { actor }) => messageService.undo(id, actor),
    markRead: ({ id }, { actor }) => messageService.markRead(id, actor),
    markUnread: ({ id }, { actor }) => messageService.markUnread(id, actor),
  },
  requestService: {
    resolve: ({ id, decision }, { actor }) => requestService.resolve(id, decision, actor),
    cancel: ({ id }, { actor }) => requestService.cancel(id, actor),
  },
  remunerationService: {
    list: (_input, { actor }) => remunerationService.list(actor),
    detail: ({ cycle, trainerId }, { actor }) => remunerationService.detail(cycle, trainerId, actor),
    approve: ({ cycle, trainerId, revision }, { actor }) => remunerationService.approve(cycle, trainerId, revision, actor),
  },
}

// Fixed Admin authority; these switches require Owner review before operational changes.
export const ADMIN_APPROVAL_FIELDS = [
  ['clientCreation', 'Create clients'], ['clientDetails', 'Edit client details and notes'],
  ['clientLifecycle', 'Deactivate or reactivate clients'], ['assessments', 'Save, correct or void assessments'],
  ['trainerCreation', 'Create Trainers'], ['trainerDetails', 'Edit Trainer details'],
  ['trainerAssignment', 'Change assignments or Trainer approval requirements'], ['trainerLifecycle', 'Deactivate or reactivate Trainers'],
  ['sessionScheduling', 'Change schedules or decide requests'], ['sessionContent', 'Change plans, outcomes or summaries'],
  ['sessionAcknowledgement', 'Acknowledge sessions'], ['packageCatalogue', 'Manage the package catalogue'],
  ['clientPackages', 'Add or manage purchased packages'], ['exerciseLibrary', 'Manage the Exercise Library'],
  ['content', 'Manage content'],
  ['progressReportSharing', 'Share progress reports'], ['sessionPdfSharing', 'Share session PDFs'],
]

export const defaultAdminApprovals = () => Object.fromEntries(ADMIN_APPROVAL_FIELDS.map(([key]) => [key, ['exerciseLibrary', 'content'].includes(key)]))

import useClientNotes from './useClientNotes.js'
import usePortalData from '../../hooks/usePortalData.js'
import usePortalActions from '../../hooks/usePortalActions.js'
import { useCallback } from 'react'
import ClientProfilePage from './ClientProfilePage.jsx'
import { activePackages } from '../../app/packages.js'
import { visibleSessionsForUser } from '../../app/sessionRules.js'
import { scheduleNotification } from '../../app/actionNotifications.js'

export default function ClientProfileRoute({ selectedClient, parts, navigate, openSession }) {
  const { snapshot, services, today } = usePortalData()
  const { runAction, reload } = usePortalActions()
  const { user, data: db, policy } = snapshot
  const { trainers } = db
  const sessions = db.sessions ?? []
  const directoryOnly = snapshot.capabilities?.directoryReadOnly === true
  const { clientService } = services
  const notes = useClientNotes(selectedClient, Boolean(snapshot.capabilities?.clientNoteWrites), clientService, snapshot.sessionGeneration)
  const progressClientId = selectedClient.id
  const previewRenewal = useCallback(draft => services.previewClientRenewalMatches({ id: selectedClient.id, draft }), [services, selectedClient.id])
  const reviewRenewal = useCallback(() => runAction(() => services.reviewClientRenewal({ id: selectedClient.id, expectedVersion: selectedClient.version })), [services, selectedClient.id, selectedClient.version, runAction])
  const loadProgressReportHistory = useCallback(packageId =>
    clientService.progressReportHistory({ id: progressClientId, packageId }), [clientService, progressClientId])
  if (notes.error) return <div role="alert"><p>{notes.error.message}</p><button type="button" onClick={notes.retry}>Retry client notes</button></div>
  if (!notes.client) return <div role="status">Loading client notes…</div>
  return (
    <ClientProfilePage
      key={selectedClient.id}
      readOnly={directoryOnly}
      renewalReadOnly={directoryOnly && !snapshot.capabilities?.clientRenewalWrites}
      renewalWorkflow={directoryOnly && snapshot.capabilities?.clientRenewalWrites ? { review: reviewRenewal, preview: previewRenewal, saved: reload } : undefined}
      reactivationWorkflow={directoryOnly && snapshot.capabilities?.clientReactivationWrites ? {
        review: () => runAction(() => services.previewClientReactivation({ id: selectedClient.id, expectedVersion: selectedClient.version })),
        preview: input => runAction(() => services.previewClientReactivationDates(input)),
        save: input => runAction(() => clientService.reactivate(input), { message: 'Client reactivated.' }),
        saved: async () => { navigate('clients', { replace: true }); await reload() },
      } : undefined}
      onReviewDeactivation={directoryOnly && snapshot.capabilities?.clientDeactivationWrites && services.previewClientDeactivation ? () => runAction(() => services.previewClientDeactivation({ id: selectedClient.id, expectedVersion: selectedClient.version })) : undefined}
      notesReadOnly={directoryOnly && !snapshot.capabilities?.clientNoteWrites}
      onNotesSaved={reload}
      personalReadOnly={directoryOnly && !snapshot.capabilities?.clientPersonalWrites}
      onGeneralSaved={reload}
      onUpdateGeneral={async (patch, reviewed) => runAction(() => clientService.update({
        id: selectedClient.id, patch, ...(directoryOnly ? { reviewed } : {}),
      }), { message: 'Client details saved.' })}
      assessmentsAvailable={!directoryOnly || Boolean(snapshot.capabilities?.clientAssessmentWorkflows)}
      assessmentApi={directoryOnly && snapshot.capabilities?.clientAssessmentWorkflows ? { services, generation: snapshot.sessionGeneration } : undefined}
      sessionViewsAvailable={!directoryOnly}
      progressRoute={parts[2] === 'progress'}
      progressPackageId={parts[2] === 'progress' ? parts[3] : undefined}
      onOpenProgressPackage={id => navigate(`clients/${selectedClient.id}/progress/${id}`, { preserveView: true })}
      onSelectProfileTab={tab => {
        if (parts[2] === 'progress') navigate(`clients/${selectedClient.id}${tab === 'progress' ? '/progress' : ''}`, { replace: true, preserveView: true })
      }}
      packages={activePackages(db)}
      policy={policy}
      packageCreditTransactions={db.packageCreditTransactions}
      onDeletePackageSessions={async options => {
        const updated = await runAction(() => clientService.deletePackageSessions({ id: selectedClient.id, options }), { tone: 'warning', message: 'Upcoming package sessions deleted.' })
        await reload()
        return updated
      }}
      onDeactivatePackage={async options => {
        const updated = await runAction(() => clientService.deactivatePackage({ id: selectedClient.id, options }), { tone: 'warning', message: 'Package deactivated.' })
        await reload()
        return updated
      }}
      onReactivatePackage={async options => {
        const updated = await runAction(() => clientService.reactivatePackage({ id: selectedClient.id, options }), { message: 'Package reactivated.' })
        await reload()
        return updated
      }}
      onRenewPackage={async draft => {
        try {
          const renewed = await runAction(() => clientService.renewPackage({ id: selectedClient.id, draft }), { message: 'Package added.' })
          if (!directoryOnly) await reload()
          return renewed
        } catch (error) {
          if (directoryOnly) {
            const refreshed = await reload()
            const recovered = refreshed?.clientRenewalRecovered
            if (error.code !== 'SAVE_UNCERTAIN' && recovered?.input.id === selectedClient.id && recovered.input.draft.requestId === draft.requestId) return runAction(async () => recovered.result, { message: 'Package added.' })
          }
          throw error
        }
      }}
      user={user}
      client={notes.client}
      clients={db.clients}
      trainer={trainers.find(item => item.id === selectedClient.trainerId)}
      trainers={trainers}
      sessions={visibleSessionsForUser(user, sessions)}
      today={today}
      onOpenSession={openSession}
      onUpdate={async (patch, reviewed) => {
        await runAction(() => clientService.update({ id: selectedClient.id, patch, ...(directoryOnly ? { reviewed } : {}) }), { message: 'Client details saved.' })
      }}
      onSaveAssessment={async options => {
        const saved = await runAction(() => clientService.saveAssessment({ id: selectedClient.id, assessment: options }), { message: 'Assessment saved.' })
        await reload()
        return saved
      }}
      timeZone={policy.timeZone}
      onRecordProgressReport={async action => {
        const saved = await clientService.recordProgressReportAction({ id: selectedClient.id, action })
        await reload()
        return saved
      }}
      onLoadProgressReportHistory={loadProgressReportHistory}
      onReassignTrainer={async draft => {
        const result = await runAction(() => clientService.reassignTrainer({ id: selectedClient.id, draft }), { message: 'Trainer permanently reassigned.' })
        await reload()
        return result
      }}
      onSaveFixedWeeklySchedule={async slots => {
        const result = await runAction(() => clientService.saveFixedWeeklySchedule({ id: selectedClient.id, slots }), result => scheduleNotification('Fixed weekly schedule', result))
        await reload()
        return result
      }}
      onDeactivate={async reviewed => {
        await runAction(() => clientService.deactivate({ id: selectedClient.id, ...(directoryOnly ? { reviewed } : {}) }), { tone: 'warning', message: 'Client deactivated.' })
        navigate('clients', { replace: true })
        await reload()
      }}
      onReactivate={async ({ dates, expected }) => {
        try {
          await runAction(() => clientService.reactivate({ id: selectedClient.id, dates, expected }), { message: 'Client reactivated.' })
        } finally { await reload() }
      }}
    />
  )
}

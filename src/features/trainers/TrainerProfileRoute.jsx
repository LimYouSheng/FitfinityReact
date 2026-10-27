import usePortalData from '../../hooks/usePortalData.js'
import usePortalActions from '../../hooks/usePortalActions.js'
import TrainerProfilePage from './TrainerProfilePage.jsx'
import { scheduleNotification } from '../../app/actionNotifications.js'

export default function TrainerProfileRoute({ trainer, ownerMode, navigate, openClient }) {
  const { snapshot, services } = usePortalData()
  const { runAction, reload } = usePortalActions()
  const { user, data: db, policy } = snapshot
  const { trainers, clients } = db
  const sessions = db.sessions ?? []
  const apiMode = snapshot.capabilities?.apiBackedWorkflows === true
  const { trainerService } = services
  return (
    <TrainerProfilePage
      key={trainer.id}
      readOnly={apiMode}
      deactivationWorkflow={apiMode && snapshot.capabilities?.trainerDeactivationWrites ? {
        review: () => runAction(() => services.reviewTrainerDeactivation({ id: trainer.id, expectedVersion: trainer.version })),
        preview: input => runAction(() => services.previewTrainerDeactivation({ id: trainer.id, ...input })),
        save: input => runAction(() => trainerService.deactivate({ id: trainer.id, ...input }), { tone: 'warning', message: 'Trainer deactivated.' }),
        saved: async () => { const result = await reload(); if (result) navigate('trainers', { replace: true }); return result },
      } : undefined}
      availabilityReadOnly={apiMode && !snapshot.capabilities?.trainerAvailabilityWrites}
      onAvailabilitySaved={reload}
      reactivationReadOnly={apiMode && !(snapshot.capabilities?.trainerReactivationWrites && services.previewTrainerReactivation)}
      onReviewReactivation={apiMode ? () => runAction(() => services.previewTrainerReactivation({ id: trainer.id, expectedVersion: trainer.version })) : undefined}
      generalReadOnly={apiMode && !snapshot.capabilities?.trainerPersonalWrites}
      onGeneralSaved={reload}
      ratesReadOnly={apiMode && !snapshot.capabilities?.trainerRateWrites}
      emailVerification={snapshot.capabilities?.trainerEmailWrites && ['owner', 'admin'].includes(user.role) ? { auth: services.auth, canCorrect: snapshot.capabilities?.trainerEmailCorrections === true, onRequest: (patch, expectedVersion) => trainerService.update({ id: trainer.id, patch, expectedVersion }) } : undefined}
      onRatesSaved={reload}
      autonomyReadOnly={apiMode && !snapshot.capabilities?.trainerApprovalWrites}
      onAutonomySaved={reload}
      activityAvailable={!apiMode}
        policy={policy}
      viewer={user}
      trainer={trainer}
      trainers={trainers}
      clients={clients}
      sessions={sessions}
      onOpenClient={openClient}
      onSaveAvailability={async (blocks, expectedVersion) => {
        try {
          return await runAction(() => trainerService.saveAvailability({ id: trainer.id, blocks, ...(apiMode ? { expectedVersion } : {}) }), result => scheduleNotification('Availability', result))
        } catch (error) {
          if (apiMode && (!error.status || error.status >= 500)) {
            const refreshed = await reload()
            const recovered = refreshed?.trainerAvailabilityRecovered
            if (error.code !== 'SAVE_UNCERTAIN' && recovered?.trainer.id === trainer.id) return runAction(async () => recovered, result => scheduleNotification('Availability', result))
          }
          throw error
        }
      }}
      onSaveAutonomy={async (settings, expectedVersion) => {
        return runAction(() => trainerService.updateAutonomy({ id: trainer.id, approvalNeeded: settings, ...(expectedVersion === undefined ? {} : { expectedVersion }) }), { message: 'Approval settings saved.' })
      }}
      onUpdate={async (patch, expectedVersion) => {
        await runAction(() => trainerService.update({ id: trainer.id, patch, ...(apiMode ? { expectedVersion } : {}) }), { message: 'Trainer details saved.' })
      }}
      onDeactivate={ownerMode ? async replacements => {
        await runAction(() => trainerService.deactivate({ id: trainer.id, replacements }), { tone: 'warning', message: 'Trainer deactivated.' })
        await reload()
        navigate('trainers', { replace: true })
      } : undefined}
      onReactivate={ownerMode ? async reviewed => {
        await runAction(() => trainerService.reactivate({ id: trainer.id, ...(apiMode ? { reviewed } : {}) }), { message: 'Trainer reactivated.' })
        await reload()
      } : undefined}
    />
  )
}

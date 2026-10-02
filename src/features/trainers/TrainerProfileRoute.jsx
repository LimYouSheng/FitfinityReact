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
  const directoryOnly = snapshot.capabilities?.directoryReadOnly === true
  const { trainerService } = services
  return (
    <TrainerProfilePage
      key={trainer.id}
      readOnly={directoryOnly}
      activityAvailable={!directoryOnly}
        policy={policy}
      viewer={user}
      trainer={trainer}
      trainers={trainers}
      clients={clients}
      sessions={sessions}
      onOpenClient={openClient}
      onSaveAvailability={async blocks => {
        const result = await runAction(() => trainerService.saveAvailability({ id: trainer.id, blocks }), result => scheduleNotification('Availability', result))
        await reload()
        return result
      }}
      onSaveAutonomy={async settings => {
        await runAction(() => trainerService.updateAutonomy({ id: trainer.id, approvalNeeded: settings }), { message: 'Approval settings saved.' })
        await reload()
      }}
      onUpdate={async patch => {
        await runAction(() => trainerService.update({ id: trainer.id, patch }), { message: 'Trainer details saved.' })
        await reload()
      }}
      onDeactivate={ownerMode ? async replacements => {
        await runAction(() => trainerService.deactivate({ id: trainer.id, replacements }), { tone: 'warning', message: 'Trainer deactivated.' })
        await reload()
        navigate('trainers', { replace: true })
      } : undefined}
      onReactivate={ownerMode ? async () => {
        await runAction(() => trainerService.reactivate({ id: trainer.id }), { message: 'Trainer reactivated.' })
        await reload()
      } : undefined}
    />
  )
}

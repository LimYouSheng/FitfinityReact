import usePortalData from '../../hooks/usePortalData.js'
import usePortalActions from '../../hooks/usePortalActions.js'
import SessionDetailsPage from './SessionDetailsPage.jsx'
import { managesOperations } from '../../app/permissions.js'
import { planNotification, scheduleNotification } from '../../app/actionNotifications.js'

export default function SessionDetailsRoute({ selectedSession, navigate, openClient }) {
  const { snapshot, services, today } = usePortalData()
  const { runAction, reload } = usePortalActions()
  const { user, data: db, policy } = snapshot
  const { clients, trainers, exerciseLibrary: libraryExercises } = db
  const messages = db.messages ?? []
  const { sessionService } = services
  const sessionClient = clients.find(item => item.id === selectedSession.clientId)
  const sessionTrainer = trainers.find(item => item.id === selectedSession.trainerId)
  return (
    <SessionDetailsPage
      key={selectedSession.id}
      today={today}
      policy={policy}
      user={user}
      session={selectedSession}
      messages={messages}
      exerciseCatalog={libraryExercises}
      client={sessionClient}
      trainer={sessionTrainer}
      trainers={trainers}
      onOpenClient={() => openClient(sessionClient.id)}
      onOpenTrainer={() => navigate(managesOperations(user) ? `trainers/${sessionTrainer.id}` : 'my-profile')}
      onLoadVideo={exerciseId => sessionService.loadVideo({ sessionId: selectedSession.id, exerciseId })}
      onSaveVideo={async (exerciseId, blob, metadata) => { const result = await runAction(() => sessionService.saveVideo({ sessionId: selectedSession.id, exerciseId, file: blob, metadata }), { message: 'Exercise video saved.' }); await reload(); return result }}
      onRemoveVideo={async exerciseId => { await runAction(() => sessionService.removeVideo({ sessionId: selectedSession.id, exerciseId }), { tone: 'warning', message: 'Exercise video removed.' }); await reload() }}
      onSavePlan={async items => {
        await runAction(() => sessionService.saveExercisePlan({ sessionId: selectedSession.id, items }), planNotification(selectedSession.exercisePlan ?? [], items))
        await reload()
      }}
      onAcknowledge={async acknowledgement => {
        await runAction(() => sessionService.acknowledge({ sessionId: selectedSession.id, acknowledgement }), { message: 'Session acknowledgement saved.' })
        await reload()
      }}
      onSaveOutcome={async outcome => {
        await runAction(() => sessionService.saveOutcome({ sessionId: selectedSession.id, outcome }), { message: 'Session outcome saved.' })
        await reload()
      }}
      onSaveClientSummary={async summary => {
        await runAction(() => sessionService.saveClientSummary({ sessionId: selectedSession.id, summary }), { message: 'Client summary saved.' })
        await reload()
      }}
      onSaveDetails={async patch => {
        await runAction(() => sessionService.updateDetails({ sessionId: selectedSession.id, patch }), { message: 'Session details saved.' })
        await reload()
      }}
      onRequestTimeChange={async patch => {
        const result = await runAction(() => sessionService.requestTimeChange({ sessionId: selectedSession.id, patch }), result => scheduleNotification('Session time', result))
        await reload()
        return result
      }}
      onPreviewPostponement={() => sessionService.previewPostponement({ sessionId: selectedSession.id })}
      onPostpone={async (expected, requestKey) => {
        const result = await runAction(() => sessionService.postpone({ sessionId: selectedSession.id, expected, requestKey }), result => ({ message: result.outcome === 'requested' ? 'Postponement sent for approval.' : 'Sessions postponed. Undo is available in Messages for 24 hours.' }))
        await reload()
        return result
      }}
      onRequestTrainerChange={async trainerId => {
        const result = await runAction(() => sessionService.requestTrainerChange({ sessionId: selectedSession.id, replacementTrainerId: trainerId }), result => scheduleNotification('Trainer change', result))
        await reload()
        return result
      }}
    />
  )
}

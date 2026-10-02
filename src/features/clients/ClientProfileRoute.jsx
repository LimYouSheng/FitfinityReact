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
  const progressClientId = selectedClient.id
  const loadProgressReportHistory = useCallback(packageId =>
    clientService.progressReportHistory({ id: progressClientId, packageId }), [clientService, progressClientId])
  return (
    <ClientProfilePage
      key={selectedClient.id}
      readOnly={directoryOnly}
      assessmentsAvailable={!directoryOnly}
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
      onRenewPackage={async draft => {
        const renewed = await runAction(() => clientService.renewPackage({ id: selectedClient.id, draft }), { message: 'Package added.' })
        await reload()
        return renewed
      }}
      user={user}
      client={selectedClient}
      clients={db.clients}
      trainer={trainers.find(item => item.id === selectedClient.trainerId)}
      trainers={trainers}
      sessions={visibleSessionsForUser(user, sessions)}
      today={today}
      onOpenSession={openSession}
      onUpdate={async patch => {
        await runAction(() => clientService.update({ id: selectedClient.id, patch }), { message: 'Client details saved.' })
        await reload()
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
      onDeactivate={async () => {
        await runAction(() => clientService.deactivate({ id: selectedClient.id }), { tone: 'warning', message: 'Client deactivated.' })
        await reload()
        navigate('clients', { replace: true })
      }}
      onReactivate={async ({ dates, expected }) => {
        try {
          await runAction(() => clientService.reactivate({ id: selectedClient.id, dates, expected }), { message: 'Client reactivated.' })
        } finally { await reload() }
      }}
    />
  )
}

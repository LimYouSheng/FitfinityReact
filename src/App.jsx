import PackagesPage from './features/setup/PackagesPage.jsx'
import { packageDefinitions, activePackages } from './app/packages.js'
import { packageService } from './services/packageService.js'
import { useMemo, useState } from 'react'
import AppShell from './components/AppShell.jsx'
import DashboardPage from './features/dashboard/DashboardPage.jsx'
import ClientsPage from './features/clients/ClientsPage.jsx'
import AddClientPage from './features/clients/AddClientPage.jsx'
import ClientProfilePage from './features/clients/ClientProfilePage.jsx'
import TrainersPage from './features/trainers/TrainersPage.jsx'
import AddTrainerPage from './features/trainers/AddTrainerPage.jsx'
import TrainerProfilePage from './features/trainers/TrainerProfilePage.jsx'
import ExerciseLibraryPage from './features/exercises/ExerciseLibraryPage.jsx'
import { exerciseLibraryService } from './services/exerciseLibraryService.js'
import MessagesPage from './features/messages/MessagesPage.jsx'
import RemunerationPage from './features/remuneration/RemunerationPage.jsx'
import { remunerationService } from './services/remunerationService.js'
import { requestService } from './services/requestService.js'
import SessionsPage from './features/sessions/SessionsPage.jsx'
import SessionDetailsPage from './features/sessions/SessionDetailsPage.jsx'
import MigrationPlaceholder from './features/placeholders/MigrationPlaceholder.jsx'
import useSwipeBack from './hooks/useSwipeBack.js'
import useAppNavigation from './hooks/useAppNavigation.js'
import useZoomLock from './hooks/useZoomLock.js'
import { clientService } from './services/clientService.js'
import { trainerService } from './services/trainerService.js'
import { mockDb } from './services/mockDb.js'
import { messageService } from './services/messageService.js'
import { sessionService } from './services/sessionService.js'
import { visibleSessionsForUser } from './app/sessionRules.js'
import { useEditGuard } from './components/EditGuardProvider.jsx'
import { useNotifications } from './components/NotificationProvider.jsx'
import { exerciseNotification, planNotification, scheduleNotification } from './app/actionNotifications.js'

export default function App() {
  useZoomLock()
  const { guardNavigation } = useEditGuard()
  const { runAction, notify, clear } = useNotifications()
  const [db, setDb] = useState(() => mockDb.read())

  const [userId, setUserId] = useState(() =>
    db.users.find(user => user.role === 'owner')?.id ?? db.users[0].id
  )

  const { path, navigate, goBack, replacePath } = useAppNavigation()

  const user =
    db.users.find(item =>
      item.id === userId &&
      (item.status ?? 'active') === 'active'
    ) ??
    db.users.find(item => item.role === 'owner') ??
    db.users[0]

  const reload = () => setDb(mockDb.read())

  const switchUser = id => guardNavigation(() => {
    clear()
    setUserId(id)
    replacePath('dashboard')
  })

  const reset = () => guardNavigation(async () => {
    let fresh
    try {
      fresh = await runAction(() => mockDb.reset(), null)
    } catch { return }
    clear()
    notify({ tone: 'warning', message: 'Demo data reset.' })

    setDb(fresh)
    setUserId(
      fresh.users.find(item => item.role === 'owner')?.id ??
      fresh.users[0].id
    )

    replacePath('dashboard')
  })

  const libraryExercises = useMemo(() => exerciseLibraryService.getAll(user), [db, user])

  const clients = db.clients
  const trainers = db.trainers
  const sessions = db.sessions ?? []
  const messages = db.messages ?? []

  const parts = path.split('/').filter(Boolean)
  const route = parts[0] || 'dashboard'
  const detailId = parts[1] ?? null
  const creatingClient = route === 'clients' && detailId === 'new'
  const creatingTrainer = route === 'trainers' && detailId === 'new'

  const selectedClient = useMemo(
    () =>
      route === 'clients' && detailId && !creatingClient
        ? clients.find(item => item.id === detailId) ?? null
        : null,
    [clients, creatingClient, detailId, route],
  )

  const selectedTrainer = useMemo(
    () =>
      route === 'trainers' && detailId
        ? trainers.find(item => item.id === detailId) ?? null
        : null,
    [trainers, detailId, route],
  )

  const selectedSession = useMemo(
    () =>
      route === 'sessions' && detailId
        ? visibleSessionsForUser(user, sessions).find(item => item.id === detailId) ?? null
        : null,
    [detailId, route, sessions, user],
  )

  const selfTrainer =
    user.role === 'trainer'
      ? trainers.find(item => item.id === user.trainerId)
      : null

  const backFallback =
    route === 'clients'
      ? 'clients'
      : route === 'trainers'
        ? 'trainers'
        : route === 'sessions'
          ? 'sessions'
          : route === 'remuneration'
            ? (parts[2] ? `remuneration/${detailId}` : 'remuneration')
            : route === 'packages' ? 'packages' : route === 'exercises' ? 'exercises' : 'dashboard'

  useSwipeBack({
    enabled:
      creatingClient ||
      creatingTrainer ||
      Boolean(selectedClient) ||
      Boolean(selectedTrainer) ||
      Boolean(selectedSession) ||
      route === 'my-profile' ||
      route === 'owner-profile' ||
      (['remuneration', 'exercises', 'packages'].includes(route) && Boolean(detailId)),
    onBack: () => goBack(backFallback),
  })

  const openClient = id => navigate(`clients/${id}`)
  const openAddClient = () => navigate('clients/new')
  const openTrainer = id => navigate(`trainers/${id}`)
  const openAddTrainer = () => navigate('trainers/new')
  const openSession = id => navigate(`sessions/${id}`)

  const trainerProfile = (trainer, ownerMode) => (
    <TrainerProfilePage
      viewer={user}
      trainer={trainer}
      trainers={trainers}
      clients={clients}
      sessions={sessions}
      onBack={() => goBack(ownerMode ? 'trainers' : 'dashboard')}
      onOpenClient={openClient}
      onSaveAvailability={async blocks => {
        const result = await runAction(() => trainerService.saveAvailability(trainer.id, blocks, user), result => scheduleNotification('Availability', result))
        reload()
        return result
      }}
      onSaveAutonomy={async settings => {
        await runAction(() => trainerService.updateAutonomy(trainer.id, settings), { message: 'Approval settings saved.' })
        reload()
      }}
      onUpdate={async patch => {
        await runAction(() => trainerService.update(trainer.id, patch), { message: 'Trainer details saved.' })
        reload()
      }}
      onDeactivate={ownerMode ? async replacements => {
        await runAction(() => trainerService.deactivate(trainer.id, replacements), { tone: 'warning', message: 'Trainer deactivated.' })
        reload()
        navigate('trainers', { replace: true })
      } : undefined}
      onReactivate={ownerMode ? async () => {
        await runAction(() => trainerService.reactivate(trainer.id), { message: 'Trainer reactivated.' })
        reload()
      } : undefined}
    />
  )

  let page

  if (creatingClient && user.role === 'owner') {
    page = (
      <AddClientPage
        packages={activePackages(db)}
        trainers={trainers}
        onCancel={() => goBack('clients')}
        onCreate={async draft => {
          const created = await runAction(() => clientService.create(draft), { message: 'Client created.' })
          reload()
          return created
        }}
        onCreated={id => navigate(`clients/${id}`, { replace: true })}
      />
    )
  } else if (route === 'clients' && selectedClient) {
    page = (
      <ClientProfilePage
        user={user}
        client={selectedClient}
        trainer={trainers.find(item => item.id === selectedClient.trainerId)}
        trainers={trainers}
        sessions={sessions}
        onOpenSession={openSession}
        onBack={() => goBack('clients')}
        onUpdate={async patch => {
          await runAction(() => clientService.update(selectedClient.id, patch), { message: 'Client details saved.' })
          reload()
        }}
        onSaveFixedWeeklySchedule={async slots => {
          const result = await runAction(() => clientService.saveFixedWeeklySchedule(
            selectedClient.id,
            slots,
            user,
          ), result => scheduleNotification('Fixed weekly schedule', result))
          reload()
          return result
        }}
        onDeactivate={async () => {
          await runAction(() => clientService.deactivate(selectedClient.id), { tone: 'warning', message: 'Client deactivated.' })
          reload()
          navigate('clients', { replace: true })
        }}
        onReactivate={async () => {
          await runAction(() => clientService.reactivate(selectedClient.id), { message: 'Client reactivated.' })
          reload()
        }}
      />
    )
  } else if (route === 'clients') {
    page = (
      <ClientsPage
        user={user}
        clients={clients}
        trainers={trainers}
        onOpen={openClient}
        onAdd={openAddClient}
      />
    )
  } else if (creatingTrainer && user.role === 'owner') {
    page = (
      <AddTrainerPage
        trainers={trainers}
        onCancel={() => goBack('trainers')}
        onCreate={async draft => {
          const created = await runAction(() => trainerService.create(draft, user), { message: 'Trainer created.' })
          reload()
          return created
        }}
        onCreated={id => navigate(`trainers/${id}`, { replace: true })}
      />
    )
  } else if (
    route === 'trainers' &&
    user.role === 'owner' &&
    selectedTrainer
  ) {
    page = trainerProfile(selectedTrainer, true)
  } else if (route === 'trainers' && user.role === 'owner') {
    page = <TrainersPage trainers={trainers} onOpen={openTrainer} onAdd={openAddTrainer} />
  } else if (
    route === 'my-profile' &&
    user.role === 'trainer' &&
    selfTrainer
  ) {
    page = trainerProfile(selfTrainer, false)
  } else if (route === 'sessions' && selectedSession) {
    const sessionClient = clients.find(item => item.id === selectedSession.clientId)
    const sessionTrainer = trainers.find(item => item.id === selectedSession.trainerId)
    page = (
      <SessionDetailsPage
        user={user}
        session={selectedSession}
        messages={messages}
        exerciseCatalog={libraryExercises}
        client={sessionClient}
        trainer={sessionTrainer}
        trainers={trainers}
        onOpenClient={() => openClient(sessionClient.id)}
        onOpenTrainer={() => navigate(user.role === 'owner' ? `trainers/${sessionTrainer.id}` : 'my-profile')}
        onSavePlan={async items => {
          await runAction(() => sessionService.saveExercisePlan(selectedSession.id, items), planNotification(selectedSession.exercisePlan ?? [], items))
          reload()
        }}
        onAcknowledge={async acknowledgement => {
          await runAction(() => sessionService.acknowledge(selectedSession.id, acknowledgement), { message: 'Session acknowledgement saved.' })
          reload()
        }}
        onSaveOutcome={async outcome => {
          await runAction(() => sessionService.saveOutcome(selectedSession.id, outcome), { message: 'Session outcome saved.' })
          reload()
        }}
        onSaveClientSummary={async summary => {
          await runAction(() => sessionService.saveClientSummary(selectedSession.id, summary), { message: 'Client summary saved.' })
          reload()
        }}
        onMarkWhatsAppSent={async () => {
          await runAction(() => sessionService.markWhatsAppSent(selectedSession.id), { tone: 'info', message: 'Summary opened in WhatsApp.' })
          reload()
        }}
        onSaveDetails={async patch => {
          await runAction(() => sessionService.updateDetails(selectedSession.id, patch), { message: 'Session details saved.' })
          reload()
        }}
        onRequestTimeChange={async patch => {
          const result = await runAction(() => sessionService.requestTimeChange(selectedSession.id, user, patch), result => scheduleNotification('Session time', result))
          reload()
          return result
        }}
        onRequestTrainerChange={async trainerId => {
          const result = await runAction(() => sessionService.requestTrainerChange(selectedSession.id, user, trainerId), result => scheduleNotification('Trainer change', result))
          reload()
          return result
        }}
      />
    )
  } else if (route === 'sessions') {
    page = (
      <SessionsPage
        user={user}
        sessions={sessions}
        clients={clients}
        trainers={trainers}
        onOpen={openSession}
      />
    )
  } else if (route === 'messages') {
    page = (
      <MessagesPage
        user={user}
        messages={messages}
        exercises={libraryExercises}
        packages={packageDefinitions(db)}
        clients={clients}
        trainers={trainers}
        sessions={sessions}
        onResolveRequest={async (id, decision) => {
          await runAction(() => requestService.resolve(id, decision, user), { tone: decision === 'approved' ? 'success' : 'warning', message: decision === 'approved' ? 'Request approved.' : 'Request rejected.' })
          reload()
        }}
        onMarkRead={async id => {
          await runAction(() => messageService.markRead(id), null)
          reload()
        }}
        onMarkUnread={async id => {
          await runAction(() => messageService.markUnread(id), { tone: 'info', message: 'Message marked as unread.' })
          reload()
        }}
        onOpenRelated={({ type, id }) => {
          if (type === 'package') navigate(`packages/${id}`, { replace: true })
          if (type === 'exercise') navigate(`exercises/${id}`, { replace: true })
          if (type === 'remuneration') navigate(`remuneration/${id}`, { replace: true })
          if (type === 'client') navigate(`clients/${id}`, { replace: true })
          if (type === 'session') navigate(`sessions/${id}`, { replace: true })
          if (type === 'trainer') {
            navigate(user.role === 'owner' ? `trainers/${id}` : 'my-profile', { replace: true })
          }
        }}
      />
    )
  } else if (route === 'remuneration') {
    page = <RemunerationPage
      key={user.id}
      user={user}
      data={db}
      cycleKey={detailId}
      trainerId={parts[2]}
      onNavigate={navigate}
      onBack={() => goBack(detailId ? `remuneration/${detailId}` : 'remuneration')}
      onOpenSession={openSession}
      onApprove={async (cycle, trainer, revision) => {
        await runAction(() => remunerationService.approve(cycle, trainer, revision, user), { message: 'Remuneration approved.' })
        reload()
      }}
    />
  } else if (route === 'exercises') {
    page = <ExerciseLibraryPage key={user.id} user={user} exercises={libraryExercises} detailId={detailId}
      onNavigate={navigate} onBack={() => goBack('exercises')}
      onSave={async options => {
        const saved = await runAction(() => exerciseLibraryService.save(options, user), saved => exerciseNotification(libraryExercises.find(item => item.id === options.id), saved))
        reload()
        return saved
      }}
    />
  } else if (route === 'packages' && user.role === 'owner') {
    page = <PackagesPage key={detailId ?? 'list'} packages={packageDefinitions(db)} selectedId={detailId} onNavigate={navigate}
      onSave={async options => {
        const saved = await runAction(() => packageService.save(options, user), { tone: options.draft.status === 'inactive' ? 'warning' : 'success',
          message: options.draft.status === 'inactive' ? 'Package deactivated.' : options.id ? 'Package saved.' : 'Package created.' })
        reload()
        return saved
      }} />
  } else if (route === 'packages') {
    page = <div className="page-head"><div><h1>Packages</h1><p>Package setup is available to the owner.</p></div></div>
  } else if (route === 'owner-profile' && user.role === 'owner') {
    page = <MigrationPlaceholder title="Owner Profile" />
  } else if (route === 'dashboard') {
    page = <DashboardPage user={user} onAddClient={openAddClient} onAddTrainer={openAddTrainer} />
  } else {
    const title = ({
      sessions: 'All Sessions',
      remuneration: 'Remuneration',
      exercises: 'Exercise Library',
      content: 'Content Management',
    })[route] ?? 'Dashboard'

    page = <MigrationPlaceholder title={title} />
  }

  const shellCanGoBack =
    creatingClient ||
    creatingTrainer ||
    Boolean(selectedClient) ||
    Boolean(selectedTrainer) ||
    Boolean(selectedSession) ||
    route === 'my-profile' ||
    route === 'owner-profile' ||
    (['remuneration', 'exercises', 'packages'].includes(route) && Boolean(detailId))

  const shellBackFallback =
    route === 'clients'
      ? 'clients'
      : route === 'trainers'
        ? 'trainers'
        : route === 'sessions'
          ? 'sessions'
          : route === 'remuneration'
            ? (parts[2] ? `remuneration/${detailId}` : 'remuneration')
            : route === 'packages' ? 'packages' : route === 'exercises' ? 'exercises' : 'dashboard'

  return (
    <AppShell
      user={user}
      users={db.users}
      userId={user.id}
      route={route}
      canGoBack={shellCanGoBack}
      onBack={() => goBack(shellBackFallback)}
      messages={messages}
      onRoute={navigate}
      onUserChange={switchUser}
      onReset={reset}
    >
      {page}
    </AppShell>
  )
}

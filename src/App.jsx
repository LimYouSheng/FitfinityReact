import { useCallback, useEffect, useMemo, useState } from 'react'
import AppShell from './components/AppShell.jsx'
import DashboardPage from './features/dashboard/DashboardPage.jsx'
import ClientsPage from './features/clients/ClientsPage.jsx'
import ClientProfilePage from './features/clients/ClientProfilePage.jsx'
import TrainersPage from './features/trainers/TrainersPage.jsx'
import TrainerProfilePage from './features/trainers/TrainerProfilePage.jsx'
import MessagesPage from './features/messages/MessagesPage.jsx'
import SessionsPage from './features/sessions/SessionsPage.jsx'
import SessionDetailsPage from './features/sessions/SessionDetailsPage.jsx'
import MigrationPlaceholder from './features/placeholders/MigrationPlaceholder.jsx'
import useSwipeBack from './hooks/useSwipeBack.js'
import useZoomLock from './hooks/useZoomLock.js'
import { clientService } from './services/clientService.js'
import { trainerService } from './services/trainerService.js'
import { mockDb } from './services/mockDb.js'
import { messageService } from './services/messageService.js'
import { sessionService } from './services/sessionService.js'
import { visibleSessionsForUser } from './app/sessionRules.js'
import { useEditGuard } from './components/EditGuardProvider.jsx'

const pathFromLocation = () =>
  location.hash.replace(/^#\/?/, '') || 'dashboard'

const cleanPath = value =>
  String(value || 'dashboard').replace(/^\/+|\/+$/g, '') || 'dashboard'

export default function App() {
  useZoomLock()
  const { guardNavigation } = useEditGuard()
  const [db, setDb] = useState(() => mockDb.read())

  const [userId, setUserId] = useState(() =>
    db.users.find(user => user.role === 'owner')?.id ?? db.users[0].id
  )

  const [path, setPath] = useState(pathFromLocation)

  const user =
    db.users.find(item =>
      item.id === userId &&
      (item.status ?? 'active') === 'active'
    ) ??
    db.users.find(item => item.role === 'owner') ??
    db.users[0]

  useEffect(() => {
    const initialPath = pathFromLocation()
    const existingDepth = history.state?.fitfinityDepth

    history.replaceState(
      {
        ...history.state,
        fitfinity: true,
        fitfinityDepth: Number.isFinite(existingDepth) ? existingDepth : 0,
        fitfinityPath: initialPath,
      },
      '',
      location.href,
    )

    const syncFromHistory = () => setPath(pathFromLocation())

    window.addEventListener('popstate', syncFromHistory)
    window.addEventListener('hashchange', syncFromHistory)

    return () => {
      window.removeEventListener('popstate', syncFromHistory)
      window.removeEventListener('hashchange', syncFromHistory)
    }
  }, [])

  const navigate = useCallback((next, options = {}) => guardNavigation(() => {
    const nextPath = cleanPath(next)
    const currentDepth = history.state?.fitfinityDepth ?? 0

    const state = {
      fitfinity: true,
      fitfinityDepth: options.replace
        ? currentDepth
        : currentDepth + 1,
      fitfinityPath: nextPath,
    }

    if (options.replace) {
      history.replaceState(state, '', `#/${nextPath}`)
    } else {
      history.pushState(state, '', `#/${nextPath}`)
    }

    setPath(nextPath)
  }), [guardNavigation])

  const goBack = useCallback(fallback => guardNavigation(() => {
    const depth = history.state?.fitfinityDepth ?? 0

    if (depth > 0) {
      history.back()
    } else {
      const nextPath = cleanPath(fallback)
      history.replaceState({ fitfinity: true, fitfinityDepth: 0, fitfinityPath: nextPath }, '', `#/${nextPath}`)
      setPath(nextPath)
    }
  }), [guardNavigation])

  const reload = () => setDb(mockDb.read())

  const switchUser = id => guardNavigation(() => {
    const nextPath = 'dashboard'
    setUserId(id)
    history.replaceState(
      { fitfinity: true, fitfinityDepth: history.state?.fitfinityDepth ?? 0, fitfinityPath: nextPath },
      '',
      `#/${nextPath}`,
    )
    setPath(nextPath)
  })

  const reset = () => guardNavigation(() => {
    mockDb.reset()
    const fresh = mockDb.read()

    setDb(fresh)
    setUserId(
      fresh.users.find(item => item.role === 'owner')?.id ??
      fresh.users[0].id
    )

    const nextPath = 'dashboard'
    history.replaceState({ fitfinity: true, fitfinityDepth: history.state?.fitfinityDepth ?? 0, fitfinityPath: nextPath }, '', `#/${nextPath}`)
    setPath(nextPath)
  })

  const clients = db.clients
  const trainers = db.trainers
  const sessions = db.sessions ?? []
  const messages = db.messages ?? []

  const parts = path.split('/').filter(Boolean)
  const route = parts[0] || 'dashboard'
  const detailId = parts[1] ?? null

  const selectedClient = useMemo(
    () =>
      route === 'clients' && detailId
        ? clients.find(item => item.id === detailId) ?? null
        : null,
    [clients, detailId, route],
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
        : 'dashboard'

  useSwipeBack({
    enabled:
      Boolean(selectedClient) ||
      Boolean(selectedTrainer) ||
      Boolean(selectedSession) ||
      route === 'my-profile' ||
      route === 'owner-profile',
    onBack: () => goBack(backFallback),
  })

  const openClient = id => navigate(`clients/${id}`)
  const openTrainer = id => navigate(`trainers/${id}`)
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
      onSaveAutonomy={async settings => {
        await trainerService.updateAutonomy(trainer.id, settings)
        reload()
      }}
      onUpdate={async patch => {
        await trainerService.update(trainer.id, patch)
        reload()
      }}
      onDeactivate={ownerMode ? async replacements => {
        await trainerService.deactivate(trainer.id, replacements)
        reload()
        navigate('trainers', { replace: true })
      } : undefined}
      onReactivate={ownerMode ? async () => {
        await trainerService.reactivate(trainer.id)
        reload()
      } : undefined}
    />
  )

  let page

  if (route === 'clients' && selectedClient) {
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
          await clientService.update(selectedClient.id, patch)
          reload()
        }}
        onSaveFixedWeeklySchedule={async slots => {
          const result = await clientService.saveFixedWeeklySchedule(
            selectedClient.id,
            slots,
            user,
          )
          reload()
          return result
        }}
        onDeactivate={async () => {
          await clientService.deactivate(selectedClient.id)
          reload()
          navigate('clients', { replace: true })
        }}
        onReactivate={async () => {
          await clientService.reactivate(selectedClient.id)
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
      />
    )
  } else if (
    route === 'trainers' &&
    user.role === 'owner' &&
    selectedTrainer
  ) {
    page = trainerProfile(selectedTrainer, true)
  } else if (route === 'trainers' && user.role === 'owner') {
    page = <TrainersPage trainers={trainers} onOpen={openTrainer} />
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
        client={sessionClient}
        trainer={sessionTrainer}
        trainers={trainers}
        onOpenClient={() => openClient(sessionClient.id)}
        onOpenTrainer={() => navigate(user.role === 'owner' ? `trainers/${sessionTrainer.id}` : 'my-profile')}
        onSavePlan={async items => {
          await sessionService.saveExercisePlan(selectedSession.id, items)
          reload()
        }}
        onAcknowledge={async acknowledgement => {
          await sessionService.acknowledge(selectedSession.id, acknowledgement)
          reload()
        }}
        onSaveOutcome={async outcome => {
          await sessionService.saveOutcome(selectedSession.id, outcome)
          reload()
        }}
        onSaveClientSummary={async summary => {
          await sessionService.saveClientSummary(selectedSession.id, summary)
          reload()
        }}
        onMarkWhatsAppSent={async () => {
          await sessionService.markWhatsAppSent(selectedSession.id)
          reload()
        }}
        onSaveDetails={async patch => {
          await sessionService.updateDetails(selectedSession.id, patch)
          reload()
        }}
        onRequestTimeChange={async patch => {
          const result = await sessionService.requestTimeChange(selectedSession.id, user, patch)
          reload()
          return result
        }}
        onRequestTrainerChange={async trainerId => {
          const result = await sessionService.requestTrainerChange(selectedSession.id, user, trainerId)
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
        clients={clients}
        trainers={trainers}
        sessions={sessions}
        onMarkRead={async id => {
          await messageService.markRead(id)
          reload()
        }}
        onOpenRelated={({ type, id }) => {
          if (type === 'client') navigate(`clients/${id}`, { replace: true })
          if (type === 'session') navigate(`sessions/${id}`, { replace: true })
          if (type === 'trainer') {
            navigate(user.role === 'owner' ? `trainers/${id}` : 'my-profile', { replace: true })
          }
        }}
      />
    )
  } else if (route === 'owner-profile' && user.role === 'owner') {
    page = <MigrationPlaceholder title="Owner Profile" />
  } else if (route === 'dashboard') {
    page = <DashboardPage user={user} />
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
    Boolean(selectedClient) ||
    Boolean(selectedTrainer) ||
    Boolean(selectedSession) ||
    route === 'my-profile' ||
    route === 'owner-profile'

  const shellBackFallback =
    route === 'clients'
      ? 'clients'
      : route === 'trainers'
        ? 'trainers'
        : route === 'sessions'
          ? 'sessions'
        : 'dashboard'

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

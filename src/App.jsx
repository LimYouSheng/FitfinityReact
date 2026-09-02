import { useCallback, useEffect, useMemo, useState } from 'react'
import AppShell from './components/AppShell.jsx'
import DashboardPage from './features/dashboard/DashboardPage.jsx'
import ClientsPage from './features/clients/ClientsPage.jsx'
import ClientProfilePage from './features/clients/ClientProfilePage.jsx'
import TrainersPage from './features/trainers/TrainersPage.jsx'
import TrainerProfilePage from './features/trainers/TrainerProfilePage.jsx'
import MessagesPage from './features/messages/MessagesPage.jsx'
import MigrationPlaceholder from './features/placeholders/MigrationPlaceholder.jsx'
import useSwipeBack from './hooks/useSwipeBack.js'
import useZoomLock from './hooks/useZoomLock.js'
import { clientService } from './services/clientService.js'
import { trainerService } from './services/trainerService.js'
import { mockDb } from './services/mockDb.js'
import { messageService } from './services/messageService.js'

const pathFromLocation = () =>
  location.hash.replace(/^#\/?/, '') || 'dashboard'

const cleanPath = value =>
  String(value || 'dashboard').replace(/^\/+|\/+$/g, '') || 'dashboard'

export default function App() {
  useZoomLock()
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

  const navigate = useCallback((next, options = {}) => {
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
  }, [])

  const goBack = useCallback(fallback => {
    const depth = history.state?.fitfinityDepth ?? 0

    if (depth > 0) {
      history.back()
    } else {
      navigate(fallback, { replace: true })
    }
  }, [navigate])

  const reload = () => setDb(mockDb.read())

  const switchUser = id => {
    setUserId(id)
    navigate('dashboard', { replace: true })
  }

  const reset = () => {
    mockDb.reset()
    const fresh = mockDb.read()

    setDb(fresh)
    setUserId(
      fresh.users.find(item => item.role === 'owner')?.id ??
      fresh.users[0].id
    )

    navigate('dashboard', { replace: true })
  }

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

  const selfTrainer =
    user.role === 'trainer'
      ? trainers.find(item => item.id === user.trainerId)
      : null

  const backFallback =
    route === 'clients'
      ? 'clients'
      : route === 'trainers'
        ? 'trainers'
        : 'dashboard'

  useSwipeBack({
    enabled:
      Boolean(selectedClient) ||
      Boolean(selectedTrainer) ||
      route === 'my-profile' ||
      route === 'owner-profile',
    onBack: () => goBack(backFallback),
  })

  const openClient = id => navigate(`clients/${id}`)
  const openTrainer = id => navigate(`trainers/${id}`)

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
  } else if (route === 'messages') {
    page = (
      <MessagesPage
        user={user}
        messages={messages}
        onMarkRead={async id => {
          await messageService.markRead(id)
          reload()
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
    route === 'my-profile' ||
    route === 'owner-profile'

  const shellBackFallback =
    route === 'clients'
      ? 'clients'
      : route === 'trainers'
        ? 'trainers'
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

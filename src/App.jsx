import ContentManagementPage from './features/content/ContentManagementPage.jsx'
import PackagesPage from './features/setup/PackagesPage.jsx'
import { packageDefinitions, activePackages } from './app/packages.js'
import { useMemo, useRef, useState } from 'react'
import AppShell from './components/AppShell.jsx'
import DashboardPage from './features/dashboard/DashboardPage.jsx'
import ClientsPage from './features/clients/ClientsPage.jsx'
import AddClientPage from './features/clients/AddClientPage.jsx'
import ClientProfilePage from './features/clients/ClientProfilePage.jsx'
import TrainersPage from './features/trainers/TrainersPage.jsx'
import AddTrainerPage from './features/trainers/AddTrainerPage.jsx'
import TrainerProfilePage from './features/trainers/TrainerProfilePage.jsx'
import ExerciseLibraryPage from './features/exercises/ExerciseLibraryPage.jsx'
import MessagesPage, { MessageInbox } from './features/messages/MessagesPage.jsx'
import { MESSAGE_CATEGORIES } from './features/messages/messageFilters.js'
import RemunerationPage from './features/remuneration/RemunerationPage.jsx'
import SessionsPage from './features/sessions/SessionsPage.jsx'
import SessionDetailsPage from './features/sessions/SessionDetailsPage.jsx'
import UnavailablePage from './features/placeholders/UnavailablePage.jsx'
import OwnerProfilePage from './features/owner/OwnerProfilePage.jsx'
import useSwipeBack from './hooks/useSwipeBack.js'
import useAppNavigation from './hooks/useAppNavigation.js'
import useZoomLock from './hooks/useZoomLock.js'
import { visibleClientsForUser } from './app/status.js'
import { PortalDataProvider } from './components/PortalDataProvider.jsx'
import usePortalData from './hooks/usePortalData.js'
import SignInPage from './features/account/SignInPage.jsx'
import ChangePasswordPage from './features/account/ChangePasswordPage.jsx'
import { visibleSessionsForUser } from './app/sessionRules.js'
import { useEditGuard } from './components/EditGuardProvider.jsx'
import { useNotifications } from './components/NotificationProvider.jsx'
import { exerciseNotification, planNotification, scheduleNotification } from './app/actionNotifications.js'

export default function App({ services }) {
  return <PortalDataProvider services={services}><PortalRoot /></PortalDataProvider>
}

function PortalRoot() {
  const { snapshot, error, loading, refresh, services } = usePortalData()
  if (loading) return <main className="account-entry"><p role="status">Loading staff portal…</p></main>
  if (!snapshot) return <main className="account-entry"><h1>Unable to load the portal</h1><p role="alert">{error}</p><button className="primary-button" onClick={() => void refresh().catch(() => {})}>Retry</button></main>
  if (!snapshot.user) return <SignInPage accounts={snapshot.accounts} demoPassword={snapshot.demoPassword} onSignIn={async credentials => { await services.auth.signIn(credentials); await refresh() }} />
  return <>{error && <div className="portal-load-error" role="alert">{error} <button onClick={() => void refresh().catch(() => {})}>Retry loading</button></div>}<StaffPortal key={snapshot.user.id} /></>
}

function StaffPortal() {
  useZoomLock()
  const { guardNavigation } = useEditGuard()
  const { runAction, notify, clear } = useNotifications()
  const { snapshot, refresh: refreshData, services, today } = usePortalData()
  // A committed save stays successful even if its follow-up refresh fails.
  // The provider keeps a retry banner; do not invite duplicate writes.
  const reload = () => refreshData().catch(() => null)
  const { user, data: db, policy } = snapshot
  const [accountBusy, setAccountBusy] = useState(false)
  const switchingAccount = useRef(false)
  const [calendarState, setCalendarState] = useState(() => ({ mode: 'week', date: today }))
  const { clientService, trainerService, sessionService, exerciseLibraryService, packageService, messageService, requestService, remunerationService } = services
  const { path, navigate, goBack, replacePath } = useAppNavigation()

  const switchUser = id => guardNavigation(async () => {
    if (switchingAccount.current || id === user.id) return
    switchingAccount.current = true
    setAccountBusy(true)
    try {
      await runAction(() => services.auth.switchDemoIdentity(id), null)
      clear(); replacePath('dashboard'); await reload()
    } catch { /* The shared notification reports the failed account change. */ }
    finally { switchingAccount.current = false; setAccountBusy(false) }
  })
  const signOut = () => guardNavigation(async () => {
    try { await runAction(() => services.auth.signOut(), null) } catch { return }
    clear(); replacePath('dashboard'); await reload()
  })
  const reset = () => guardNavigation(async () => {
    try { await runAction(() => services.reset(), null) } catch { return }
    clear(); notify({ tone: 'warning', message: 'Demo data reset.' })
    replacePath('dashboard'); await reload()
  })
  const libraryExercises = db.exerciseLibrary

  const clients = db.clients
  const trainers = db.trainers
  const sessions = db.sessions ?? []
  const messages = db.messages ?? []

  const parts = path.split('/').filter(Boolean)
  const route = parts[0] || 'dashboard'
  const detailId = parts[1] ?? null
  const calendarDay = route === 'dashboard' && detailId === 'day' && /^\d{4}-\d{2}-\d{2}$/.test(parts[2] ?? '') ? parts[2] : null
  const creatingClient = route === 'clients' && detailId === 'new'
  const creatingTrainer = route === 'trainers' && detailId === 'new'

  const selectedClient = useMemo(
    () =>
      route === 'clients' && detailId && !creatingClient
        ? visibleClientsForUser(user, clients).find(item => item.id === detailId) ?? null
        : null,
    [clients, creatingClient, detailId, route, user],
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
            : route === 'packages' ? 'packages' : route === 'exercises' ? 'exercises' : route === 'content' ? 'content' : 'dashboard'

  useSwipeBack({
    enabled:
      creatingClient ||
      creatingTrainer ||
      Boolean(selectedClient) ||
      Boolean(selectedTrainer) ||
      Boolean(selectedSession) ||
      Boolean(calendarDay) ||
      route === 'my-profile' ||
      route === 'change-password' ||
      route === 'owner-profile' ||
      (['remuneration', 'exercises', 'packages', 'content'].includes(route) && Boolean(detailId)),
    onBack: () => goBack(backFallback),
  })

  const openClient = id => navigate(`clients/${id}`)
  const openAddClient = () => navigate('clients/new')
  const openTrainer = id => navigate(`trainers/${id}`)
  const openAddTrainer = () => navigate('trainers/new')
  const openSession = id => navigate(`sessions/${id}`)

  const trainerProfile = (trainer, ownerMode) => (
    <TrainerProfilePage
        policy={policy}
      viewer={user}
      trainer={trainer}
      trainers={trainers}
      clients={clients}
      sessions={sessions}
      onBack={() => goBack(ownerMode ? 'trainers' : 'dashboard')}
      onOpenClient={openClient}
      onSaveAvailability={async blocks => {
        const result = await runAction(() => trainerService.saveAvailability(trainer.id, blocks, user), result => scheduleNotification('Availability', result))
        await reload()
        return result
      }}
      onSaveAutonomy={async settings => {
        await runAction(() => trainerService.updateAutonomy(trainer.id, settings), { message: 'Approval settings saved.' })
        await reload()
      }}
      onUpdate={async patch => {
        await runAction(() => trainerService.update(trainer.id, patch), { message: 'Trainer details saved.' })
        await reload()
      }}
      onDeactivate={ownerMode ? async replacements => {
        await runAction(() => trainerService.deactivate(trainer.id, replacements), { tone: 'warning', message: 'Trainer deactivated.' })
        await reload()
        navigate('trainers', { replace: true })
      } : undefined}
      onReactivate={ownerMode ? async () => {
        await runAction(() => trainerService.reactivate(trainer.id), { message: 'Trainer reactivated.' })
        await reload()
      } : undefined}
    />
  )

  const messageInboxProps = {
    user,
    messages,
    contentEntries: db.contentEntries,
    exercises: libraryExercises,
    packages: packageDefinitions(db),
    clients,
    trainers,
    sessions,
    onResolveRequest: async (id, decision) => {
      await runAction(() => requestService.resolve(id, decision, user), {
        tone: decision === 'approved' ? 'success' : 'warning',
        message: decision === 'approved' ? 'Request approved.' : 'Request rejected.',
      })
      await reload()
    },
    onMarkRead: async id => {
      await runAction(() => messageService.markRead(id), null)
      await reload()
    },
    onMarkUnread: async id => {
      await runAction(() => messageService.markUnread(id), { tone: 'info', message: 'Message marked as unread.' })
      await reload()
    },
    onOpenRelated: ({ type, id }) => {
      if (type === 'content') navigate(`content/${id}`, { replace: true })
      if (type === 'package') navigate(`packages/${id}`, { replace: true })
      if (type === 'exercise') navigate(`exercises/${id}`, { replace: true })
      if (type === 'remuneration') navigate(`remuneration/${id}`, { replace: true })
      if (type === 'client') navigate(`clients/${id}`, { replace: true })
      if (type === 'session') navigate(`sessions/${id}`, { replace: true })
      if (type === 'trainer') navigate(user.role === 'owner' ? `trainers/${id}` : 'my-profile', { replace: true })
    },
  }

  let page

  if (creatingClient && user.role === 'owner') {
    page = (
      <AddClientPage
        policy={policy}
        packages={activePackages(db)}
        trainers={trainers}
        onCancel={() => goBack('clients')}
        onCreate={async draft => {
          const created = await runAction(() => clientService.create(draft), { message: 'Client created.' })
          await reload()
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
        sessions={visibleSessionsForUser(user, sessions)}
        today={today}
        onOpenSession={openSession}
        onBack={() => goBack('clients')}
        onUpdate={async patch => {
          await runAction(() => clientService.update(selectedClient.id, patch), { message: 'Client details saved.' })
          await reload()
        }}
        onSaveFixedWeeklySchedule={async slots => {
          const result = await runAction(() => clientService.saveFixedWeeklySchedule(
            selectedClient.id,
            slots,
            user,
          ), result => scheduleNotification('Fixed weekly schedule', result))
          await reload()
          return result
        }}
        onDeactivate={async () => {
          await runAction(() => clientService.deactivate(selectedClient.id), { tone: 'warning', message: 'Client deactivated.' })
          await reload()
          navigate('clients', { replace: true })
        }}
        onReactivate={async () => {
          await runAction(() => clientService.reactivate(selectedClient.id), { message: 'Client reactivated.' })
          await reload()
        }}
      />
    )
  } else if (route === 'clients' && detailId) {
    page = <UnavailablePage message="This client is unavailable for your account." />
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
        policy={policy}
        trainers={trainers}
        onCancel={() => goBack('trainers')}
        onCreate={async draft => {
          const created = await runAction(() => trainerService.create(draft, user), { message: 'Trainer created.' })
          await reload()
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
        policy={policy}
        user={user}
        session={selectedSession}
        messages={messages}
        exerciseCatalog={libraryExercises}
        client={sessionClient}
        trainer={sessionTrainer}
        trainers={trainers}
        onOpenClient={() => openClient(sessionClient.id)}
        onOpenTrainer={() => navigate(user.role === 'owner' ? `trainers/${sessionTrainer.id}` : 'my-profile')}
        onLoadVideo={exerciseId => sessionService.loadVideo(selectedSession.id, exerciseId)}
        onSaveVideo={async (exerciseId, blob, metadata) => { const result = await runAction(() => sessionService.saveVideo(selectedSession.id, exerciseId, blob, metadata), { message: 'Exercise video saved.' }); await reload(); return result }}
        onRemoveVideo={async exerciseId => { await runAction(() => sessionService.removeVideo(selectedSession.id, exerciseId), { tone: 'warning', message: 'Exercise video removed.' }); await reload() }}
        onSavePlan={async items => {
          await runAction(() => sessionService.saveExercisePlan(selectedSession.id, items), planNotification(selectedSession.exercisePlan ?? [], items))
          await reload()
        }}
        onAcknowledge={async acknowledgement => {
          await runAction(() => sessionService.acknowledge(selectedSession.id, acknowledgement), { message: 'Session acknowledgement saved.' })
          await reload()
        }}
        onSaveOutcome={async outcome => {
          await runAction(() => sessionService.saveOutcome(selectedSession.id, outcome), { message: 'Session outcome saved.' })
          await reload()
        }}
        onSaveClientSummary={async summary => {
          await runAction(() => sessionService.saveClientSummary(selectedSession.id, summary), { message: 'Client summary saved.' })
          await reload()
        }}
        onMarkWhatsAppOpened={async () => {
          await runAction(() => sessionService.markWhatsAppOpened(selectedSession.id), { tone: 'info', message: 'Summary opened in WhatsApp.' })
          await reload()
        }}
        onSaveDetails={async patch => {
          await runAction(() => sessionService.updateDetails(selectedSession.id, patch), { message: 'Session details saved.' })
          await reload()
        }}
        onRequestTimeChange={async patch => {
          const result = await runAction(() => sessionService.requestTimeChange(selectedSession.id, user, patch), result => scheduleNotification('Session time', result))
          await reload()
          return result
        }}
        onRequestTrainerChange={async trainerId => {
          const result = await runAction(() => sessionService.requestTrainerChange(selectedSession.id, user, trainerId), result => scheduleNotification('Trainer change', result))
          await reload()
          return result
        }}
      />
    )
  } else if (route === 'sessions' && detailId) {
    page = <UnavailablePage message="This session is unavailable for your account." />
  } else if (route === 'sessions') {
    page = (
      <SessionsPage
        today={today}
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
        {...messageInboxProps}
        category={MESSAGE_CATEGORIES.some(item => item.key === detailId) ? detailId : 'all'}
        onCategoryChange={category => navigate(category === 'all' ? 'messages' : `messages/${category}`)}
      />
    )
  } else if (route === 'remuneration') {
    page = <RemunerationPage
      key={user.id}
      user={user}
      views={db.remunerationViews}
      policy={policy}
      cycleKey={detailId}
      trainerId={parts[2]}
      onNavigate={navigate}
      onBack={() => goBack(detailId ? `remuneration/${detailId}` : 'remuneration')}
      onOpenSession={openSession}
      onApprove={async (cycle, trainer, revision) => {
        await runAction(() => remunerationService.approve(cycle, trainer, revision, user), { message: 'Remuneration approved.' })
        await reload()
      }}
    />
  } else if (route === 'exercises') {
    page = <ExerciseLibraryPage categories={policy.exerciseCategories} key={user.id} user={user} exercises={libraryExercises} detailId={detailId}
      onNavigate={navigate} onBack={() => goBack('exercises')} onLoadMedia={exerciseLibraryService.loadMedia}
      onSave={async options => {
        const saved = await runAction(() => exerciseLibraryService.save(options, user), saved => exerciseNotification(libraryExercises.find(item => item.id === options.id), saved))
        await reload()
        return saved
      }}
    />
  } else if (route === 'packages' && user.role === 'owner') {
    page = <PackagesPage validity={policy.packageValidity} key={detailId ?? 'list'} packages={packageDefinitions(db)} selectedId={detailId} onNavigate={navigate}
      onSave={async options => {
        const saved = await runAction(() => packageService.save(options, user), { tone: options.draft.status === 'inactive' ? 'warning' : 'success',
          message: options.draft.status === 'inactive' ? 'Package deactivated.' : options.id ? 'Package saved.' : 'Package created.' })
        await reload()
        return saved
      }} />
  } else if (route === 'packages') {
    page = <div className="page-head"><div><h1>Packages</h1><p>Package setup is available to the owner.</p></div></div>
  } else if (route === 'change-password') {
    page = <ChangePasswordPage policy={policy.password} onBack={() => goBack('dashboard')} onSave={async draft => { await runAction(() => services.auth.changePassword(draft), { message: 'Password changed.' }) }} />
  } else if (route === 'owner-profile' && user.role === 'owner') {
    page = <OwnerProfilePage user={user} />
  } else if (route === 'owner-profile') {
    page = <UnavailablePage message="This profile is available to the owner." />
  } else if (route === 'content' && user.role === 'owner') {
    page = <ContentManagementPage entries={db.contentEntries} detailId={detailId} onNavigate={navigate} onSave={async options => { const result = await runAction(() => services.contentService.save(options, user), { message: 'Content saved.' }); await reload(); return result }} />
  } else if (route === 'dashboard') {
    page = <DashboardPage
      renewals={<MessageInbox {...messageInboxProps} embedded category="renewals" onViewAll={() => navigate('messages/renewals')} />}
      state={calendarState} onState={setCalendarState} user={user}
      sessions={visibleSessionsForUser(user, sessions)} clients={clients} trainers={trainers}
      selectedDay={calendarDay} onOpenDay={day => navigate(`dashboard/day/${day}`)} onCloseDay={() => goBack('dashboard')}
      today={today} onOpenSession={id => navigate(`sessions/${id}`, { replace: Boolean(calendarDay) })}
      onAddClient={openAddClient} onAddTrainer={openAddTrainer}
    />
  } else {
    page = <UnavailablePage />
  }

  const shellCanGoBack =
    creatingClient ||
    creatingTrainer ||
    Boolean(selectedClient) ||
    Boolean(selectedTrainer) ||
    Boolean(selectedSession) ||
    Boolean(calendarDay) ||
    route === 'my-profile' ||
      route === 'change-password' ||
    route === 'owner-profile' ||
    (['remuneration', 'exercises', 'packages', 'content'].includes(route) && Boolean(detailId))

  const shellBackFallback =
    route === 'clients'
      ? 'clients'
      : route === 'trainers'
        ? 'trainers'
        : route === 'sessions'
          ? 'sessions'
          : route === 'remuneration'
            ? (parts[2] ? `remuneration/${detailId}` : 'remuneration')
            : route === 'packages' ? 'packages' : route === 'exercises' ? 'exercises' : route === 'content' ? 'content' : 'dashboard'

  return (
    <AppShell
      accountBusy={accountBusy}
      routePath={path}
      demoControls={snapshot.capabilities?.demoControls === true}
      user={user}
      users={db.users}
      userId={user.id}
      route={route}
      canGoBack={shellCanGoBack}
      onBack={() => goBack(shellBackFallback)}
      messages={messages}
      onRoute={navigate}
      onSignOut={signOut}
      onUserChange={switchUser}
      onReset={reset}
    >
      {page}
    </AppShell>
  )
}

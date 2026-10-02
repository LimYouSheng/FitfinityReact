import CreateAdminDialog, { AdminCreationRecovery } from './features/staff/CreateAdminDialog.jsx'
import { managesOperations, canViewRemuneration } from './app/permissions.js'
import ContentManagementPage from './features/content/ContentManagementPage.jsx'
import PackagesPage from './features/setup/PackagesPage.jsx'
import { packageDefinitions, activePackages } from './app/packages.js'
import { useEffect, useMemo, useRef, useState } from 'react'
import AppShell from './components/AppShell.jsx'
import PortraitOrientation from './components/PortraitOrientation.jsx'
import DashboardPage from './features/dashboard/DashboardPage.jsx'
import ClientsPage from './features/clients/ClientsPage.jsx'
import AddClientPage from './features/clients/AddClientPage.jsx'
import ClientProfileRoute from './features/clients/ClientProfileRoute.jsx'
import TrainersPage from './features/trainers/TrainersPage.jsx'
import AddTrainerPage from './features/trainers/AddTrainerPage.jsx'
import TrainerProfileRoute from './features/trainers/TrainerProfileRoute.jsx'
import ExerciseLibraryPage from './features/exercises/ExerciseLibraryPage.jsx'
import MessagesPage, { MessageInbox } from './features/messages/MessagesPage.jsx'
import { MESSAGE_CATEGORIES } from './features/messages/messageFilters.js'
import RemunerationPage from './features/remuneration/RemunerationPage.jsx'
import SessionsPage from './features/sessions/SessionsPage.jsx'
import SessionDetailsRoute from './features/sessions/SessionDetailsRoute.jsx'
import UnavailablePage from './features/placeholders/UnavailablePage.jsx'
import OwnerProfilePage from './features/owner/OwnerProfilePage.jsx'
import useSwipeBack from './hooks/useSwipeBack.js'
import useAppNavigation from './hooks/useAppNavigation.js'
import { PageState } from './hooks/usePageState.js'
import useZoomLock from './hooks/useZoomLock.js'
import { visibleClientsForUser } from './app/status.js'
import { PortalDataProvider } from './components/PortalDataProvider.jsx'
import usePortalData from './hooks/usePortalData.js'
import SignInPage from './features/account/SignInPage.jsx'
import StaffAccountPage from './features/account/StaffAccountPage.jsx'
import ChangePasswordPage from './features/account/ChangePasswordPage.jsx'
import { visibleSessionsForUser } from './app/sessionRules.js'
import { useEditGuard } from './components/EditGuardProvider.jsx'
import { useNotifications } from './components/NotificationProvider.jsx'
import { exerciseNotification } from './app/actionNotifications.js'

export default function App({ services }) {
  return <PortalDataProvider services={services}><PortraitOrientation /><PortalRoot /></PortalDataProvider>
}

function PortalRoot() {
  const { snapshot, loading, refresh, services, adminCreation } = usePortalData()
  if (loading) return <main className="account-entry"><p role="status">Loading staff portal…</p></main>
  const workspaceUserId = snapshot?.user?.id ?? adminCreation?.ownerId
  if (workspaceUserId) return <PortalWorkspace key={workspaceUserId} userId={workspaceUserId} />
  if (!snapshot) return <PortalUnavailable />
  const realAuth = snapshot.capabilities?.realAuthentication
  if (!snapshot.user) return <SignInPage accounts={snapshot.accounts} demoPassword={snapshot.demoPassword} policy={snapshot.policy.password} authNotice={snapshot.authNotice}
    onSignIn={async credentials => { const result = await services.auth.signIn(credentials); if (!realAuth) await refresh(); return result }}
    onChallenge={realAuth ? services.auth.challenge : undefined} onForgotPassword={realAuth ? services.auth.forgotPassword : undefined}
    onResetPassword={realAuth ? services.auth.resetPassword : undefined} onAuthenticated={refresh} />
  return null
}

function PortalUnavailable() {
  const { error, refresh, adminCreation } = usePortalData()
  return <main className="account-entry"><h1>Unable to load the portal</h1><p role="alert">{error}</p>{adminCreation && <AdminCreationRecovery creation={adminCreation} />}<button className="primary-button" onClick={() => void refresh().catch(() => {})}>Retry</button></main>
}

function PortalWorkspace({ userId }) {
  const { snapshot, error, refresh, adminCreation } = usePortalData()
  // One history owner survives directory outages without retaining private data.
  const navigation = useAppNavigation(userId)
  const creatingAdmin = navigation.path === 'owner-profile/create-admin'
  useEffect(() => {
    if (!creatingAdmin) adminCreation?.reset()
  }, [creatingAdmin, adminCreation])
  if (!snapshot) return <PortalUnavailable />
  return <>{error && <div className="portal-load-error" role="alert">{error} <button onClick={() => void refresh().catch(() => {})}>Retry loading</button></div>}<StaffPortal navigation={navigation} /></>
}

function StaffPortal({ navigation }) {
  useZoomLock()
  const { guardNavigation } = useEditGuard()
  const { runAction, notify, clear } = useNotifications()
  const { snapshot, refresh: refreshData, services, today, adminCreation } = usePortalData()
  // A committed save stays successful even if its follow-up refresh fails.
  // The provider keeps a retry banner; do not invite duplicate writes.
  const reload = () => refreshData().catch(() => null)
  const { user, data: db, policy } = snapshot
  const directoryOnly = snapshot.capabilities?.directoryReadOnly === true
  const enabledRoutes = directoryOnly ? ['dashboard', 'account', 'clients', ...(managesOperations(user) ? ['trainers', 'packages', ...(user.role === 'owner' ? ['owner-profile'] : [])] : ['my-profile']), 'change-password'] : undefined
  const [accountBusy, setAccountBusy] = useState(false)
  const switchingAccount = useRef(false)
  const { clientService, trainerService, exerciseLibraryService, packageService, messageService, requestService, remunerationService } = services
  const { path, navigate, goBack, replacePath, canGoBack, pageState } = navigation
  const calendarState = pageState.values.calendar ?? { mode: 'week', date: today }
  const setCalendarState = next => pageState.setValue('calendar', next, calendarState)

  const switchUser = id => guardNavigation(async () => {
    if (switchingAccount.current || id === user.id) return
    switchingAccount.current = true
    setAccountBusy(true)
    try {
      await runAction(() => services.auth.switchDemoIdentity({ userId: id }), null)
      clear(); replacePath('dashboard'); await reload()
    } catch { /* The shared notification reports the failed account change. */ }
    finally { switchingAccount.current = false; setAccountBusy(false) }
  })
  const signOut = () => guardNavigation(async () => {
    try { await runAction(() => services.auth.signOut(), null) } catch { return }
    clear(); await reload()
  })
  const reset = () => guardNavigation(async () => {
    try { await runAction(() => services.reset(), null) } catch { return }
    clear(); notify({ tone: 'warning', message: 'Demo data reset.' })
    replacePath('dashboard'); await reload()
  })
  const libraryExercises = db.exerciseLibrary

  const clients = db.clients
  const trainers = db.trainers
  const sessions = useMemo(() => db.sessions ?? [], [db.sessions])
  const messages = db.messages ?? []

  const parts = path.split('/').filter(Boolean)
  const route = parts[0] || 'dashboard'
  const detailId = parts[1] ?? null
  const calendarDay = route === 'dashboard' && detailId === 'day' && /^\d{4}-\d{2}-\d{2}$/.test(parts[2] ?? '') ? parts[2] : null
  const creatingAdmin = route === 'owner-profile' && detailId === 'create-admin' && user.role === 'owner'
  const creatingClient = route === 'clients' && detailId === 'new'
  const creatingTrainer = route === 'trainers' && detailId === 'new'

  const selectedClient = useMemo(
    () =>
      route === 'clients' && detailId && !creatingClient
        ? visibleClientsForUser(user, clients, sessions).find(item => item.id === detailId) ?? null
        : null,
    [clients, sessions, creatingClient, detailId, route, user],
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

  const backFallback = parts.length > 1
    ? (route === 'clients' && parts[2] === 'progress' ? `clients/${detailId}${parts[3] ? '/progress' : ''}` : route === 'remuneration' && parts[2] && managesOperations(user) ? `remuneration/${detailId}` : route)
    : 'dashboard'
  const back = () => goBack(backFallback)
  useSwipeBack({ enabled: canGoBack, onBack: back, routeKey: `${user.id}/${path}`,
    surface: creatingAdmin ? '.create-admin-dialog' : calendarDay ? '.calendar-day-dialog' : '.portal-main' })

  const openClient = id => navigate(`clients/${id}`)
  const openAddClient = () => navigate('clients/new')
  const openTrainer = id => navigate(`trainers/${id}`)
  const openAddTrainer = () => navigate('trainers/new')
  const openSession = id => navigate(`sessions/${id}`)

  const messageInboxProps = {
    user,
    timeZone: policy.timeZone,
    messages,
    contentEntries: db.contentEntries,
    exercises: libraryExercises,
    packages: packageDefinitions(db),
    clients,
    trainers,
    sessions,
    onResolveRequest: async (id, decision) => {
      await runAction(() => requestService.resolve({ id, decision }), {
        tone: decision === 'approved' ? 'success' : 'warning',
        message: decision === 'approved' ? 'Request approved.' : 'Request rejected.',
      })
      await reload()
    },
    onCancelRequest: async id => {
      await runAction(() => requestService.cancel({ id }), { message: 'Request cancelled.' })
      await reload()
    },
    onMarkRead: async id => {
      await runAction(() => messageService.markRead({ id }), null)
      await reload()
    },
    onMarkUnread: async id => {
      await runAction(() => messageService.markUnread({ id }), { tone: 'info', message: 'Message marked as unread.' })
      await reload()
    },
    onOpenRelated: ({ type, id }) => {
      if (type === 'content') navigate(`content/${id}`, { replace: true })
      if (type === 'package') navigate(`packages/${id}`, { replace: true })
      if (type === 'exercise') navigate(`exercises/${id}`, { replace: true })
      if (type === 'remuneration') navigate(`remuneration/${id}`, { replace: true })
      if (type === 'client') navigate(`clients/${id}`, { replace: true })
      if (type === 'session') navigate(`sessions/${id}`, { replace: true })
      if (type === 'trainer') navigate(managesOperations(user) ? `trainers/${id}` : 'my-profile', { replace: true })
    },
  }

  let page

  if (directoryOnly && (!enabledRoutes.includes(route) || creatingClient || creatingTrainer || (route === 'packages' && detailId === 'new') || (route === 'clients' && parts[2]))) {
    page = <UnavailablePage message="This workflow is not available yet." />
  } else if (creatingClient && managesOperations(user)) {
    page = (
      <AddClientPage
        user={user}
        clients={clients}
        sessions={sessions}
        policy={policy}
        packages={activePackages(db)}
        trainers={trainers}
        onCancel={() => goBack('clients')}
        onCreate={async draft => {
          const created = await runAction(() => clientService.create({ draft }), { message: 'Client created.' })
          await reload()
          return created
        }}
        onCreated={id => navigate(`clients/${id}`, { replace: true })}
      />
    )
  } else if (route === 'clients' && selectedClient) {
    page = (
      <ClientProfileRoute key={selectedClient.id} selectedClient={selectedClient}
        parts={parts} navigate={navigate} goBack={goBack} openSession={openSession} />
    )
  } else if (route === 'clients' && detailId) {
    page = <UnavailablePage message="This client is unavailable for your account." />
  } else if (route === 'clients') {
    page = (
      <ClientsPage
        sessions={sessions}
        user={user}
        clients={clients}
        trainers={trainers}
        onOpen={openClient}
        onAdd={directoryOnly ? undefined : openAddClient}
      />
    )
  } else if (creatingTrainer && managesOperations(user)) {
    page = (
      <AddTrainerPage
        viewer={user}
        policy={policy}
        trainers={trainers}
        onCancel={() => goBack('trainers')}
        onCreate={async draft => {
          const created = await runAction(() => trainerService.create({ draft }), { message: 'Trainer created.' })
          await reload()
          return created
        }}
        onCreated={id => navigate(`trainers/${id}`, { replace: true })}
      />
    )
  } else if (
    route === 'trainers' &&
    managesOperations(user) &&
    selectedTrainer
  ) {
    page = <TrainerProfileRoute key={selectedTrainer.id} trainer={selectedTrainer} ownerMode navigate={navigate} goBack={goBack} openClient={openClient} />
  } else if (route === 'trainers' && managesOperations(user)) {
    page = <TrainersPage trainers={trainers} onOpen={openTrainer} onAdd={directoryOnly ? undefined : openAddTrainer} />
  } else if (
    route === 'my-profile' &&
    user.role === 'trainer' &&
    selfTrainer
  ) {
    page = <TrainerProfileRoute key={selfTrainer.id} trainer={selfTrainer} ownerMode={false} navigate={navigate} goBack={goBack} openClient={openClient} />
  } else if (route === 'sessions' && selectedSession) {
    page = <SessionDetailsRoute key={selectedSession.id} selectedSession={selectedSession}
      navigate={navigate} openClient={openClient} />
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
        category={MESSAGE_CATEGORIES.some(item => item.key === detailId && (item.key !== 'remuneration' || canViewRemuneration(user))) ? detailId : 'all'}
        onCategoryChange={category => navigate(category === 'all' ? 'messages' : `messages/${category}`, { preserveView: true })}
      />
    )
  } else if (route === 'remuneration' && !canViewRemuneration(user)) {
    page = <UnavailablePage message="Remuneration is unavailable for this account." />
  } else if (route === 'remuneration') {
    page = <RemunerationPage
      key={user.id}
      user={user}
      views={db.remunerationViews}
      policy={policy}
      cycleKey={detailId}
      trainerId={parts[2]}
      onNavigate={(next, options) => navigate(next, { ...options, preserveView: true })}
      onOpenSession={openSession}
      onApprove={async (cycle, trainer, revision) => {
        await runAction(() => remunerationService.approve({ cycle, trainerId: trainer, revision }), { message: 'Remuneration approved.' })
        await reload()
      }}
    />
  } else if (route === 'exercises') {
    page = <ExerciseLibraryPage categories={policy.exerciseCategories} key={user.id} user={user} exercises={libraryExercises} detailId={detailId}
      onNavigate={navigate} onBack={() => goBack('exercises')} onLoadMedia={id => exerciseLibraryService.loadMedia({ id })}
      onSave={async options => {
        const saved = await runAction(() => exerciseLibraryService.save(options), saved => exerciseNotification(libraryExercises.find(item => item.id === options.id), saved))
        await reload()
        return saved
      }}
    />
  } else if (route === 'packages' && managesOperations(user)) {
    page = <PackagesPage readOnly={directoryOnly} policy={policy} key={detailId ?? 'list'} packages={packageDefinitions(db)} selectedId={detailId} onNavigate={navigate} onBack={() => goBack('packages')}
      onSave={async options => {
        const saved = await runAction(() => packageService.save(options), { tone: options.draft.status === 'inactive' ? 'warning' : 'success',
          message: options.draft.status === 'inactive' ? 'Package deactivated.' : options.id ? 'Package saved.' : 'Package created.' })
        await reload()
        return saved
      }} />
  } else if (route === 'packages') {
    page = <div className="page-head"><div><h1>Packages</h1><p>Package setup is available to the owner.</p></div></div>
  } else if (route === 'change-password') {
    page = <ChangePasswordPage key={`${user.id}/${snapshot.sessionGeneration ?? 'demo'}`} policy={policy.password} onBack={() => goBack('dashboard')} onSave={async draft => { await runAction(() => services.auth.changePassword(draft), { message: 'Password changed.' }) }} />
  } else if (route === 'owner-profile' && user.role === 'owner') {
    page = <OwnerProfilePage user={user} />
  } else if (route === 'owner-profile') {
    page = <UnavailablePage message="This profile is available to the owner." />
  } else if (route === 'content' && managesOperations(user)) {
    page = <ContentManagementPage entries={db.contentEntries} detailId={detailId} onNavigate={navigate} onBack={() => goBack('content')} onSave={async options => { const result = await runAction(() => services.contentService.save(options), { message: 'Content saved.' }); await reload(); return result }} />
  } else if (route === 'account' || (directoryOnly && route === 'dashboard')) {
    page = <StaffAccountPage user={user} profile={route === 'account'} readOnly={directoryOnly} onNavigate={navigate} onSignOut={signOut} busy={accountBusy} />
  } else if (route === 'dashboard') {
    page = <DashboardPage
      renewals={<MessageInbox {...messageInboxProps} embedded category="renewals" onViewAll={() => navigate('messages/renewals')} />}
      state={calendarState} onState={setCalendarState} user={user}
      sessions={visibleSessionsForUser(user, sessions)} clients={clients} trainers={trainers}
      selectedDay={calendarDay} onOpenDay={day => navigate(`dashboard/day/${day}`, { preserveView: true })} onCloseDay={() => goBack('dashboard')}
      today={today} onOpenSession={id => navigate(`sessions/${id}`, { replace: Boolean(calendarDay) })}
      onAddClient={openAddClient} onAddTrainer={openAddTrainer}
    />
  } else {
    page = <UnavailablePage />
  }

  return (
    <PageState.Provider value={pageState}><AppShell
      accountBusy={accountBusy}
      enabledRoutes={enabledRoutes}
      routePath={path}
      demoControls={snapshot.capabilities?.demoControls === true}
      user={user}
      users={db.users}
      userId={user.id}
      route={route}
      canGoBack={canGoBack}
      onBack={back}
      messages={messages}
      onRoute={navigate}
      onSignOut={signOut}
      onUserChange={switchUser}
      onReset={reset}
    >
      {page}
      {creatingAdmin && adminCreation && <CreateAdminDialog today={today} creation={adminCreation} realAuthentication={snapshot.capabilities?.realAuthentication === true}
        onClose={() => goBack('owner-profile')} onCreate={async (body, key) => {
          const created = await services.staffService.createAdmin({ body, requestKey: key })
          await reload()
          return created
        }} />}
    </AppShell></PageState.Provider>
  )
}

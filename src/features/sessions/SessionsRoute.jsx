import { useMemo } from 'react'
import usePortalData from '../../hooks/usePortalData.js'
import { visibleSessionsForUser } from '../../app/sessionRules.js'
import UnavailablePage from '../placeholders/UnavailablePage.jsx'
import SessionAcknowledgementRecovery from './SessionAcknowledgementRecovery.jsx'
import SessionSummaryRecovery from './SessionSummaryRecovery.jsx'
import SessionOutcomeRecovery from './SessionOutcomeRecovery.jsx'
import SessionPlanRecovery from './SessionPlanRecovery.jsx'
import SessionChangeRecovery from './SessionChangeRecovery.jsx'
import ApiSessionDetailsRoute from './ApiSessionDetailsRoute.jsx'
import SessionDetailsRoute from './SessionDetailsRoute.jsx'
import SessionsPage from './SessionsPage.jsx'

/** Recovery precedes detail selection; session keys retire editors on record changes. */
export default function SessionsRoute({ detailId, clients, trainers, navigate, openClient, onChangeSaved }) {
  const { snapshot, services, today } = usePortalData()
  const { user, data, sessionGeneration, capabilities } = snapshot
  const sessions = data.sessions
  const apiMode = capabilities?.apiBackedWorkflows === true
  const selectedSession = useMemo(() => detailId
    ? visibleSessionsForUser(user, sessions ?? []).find(item => item.id === detailId) ?? null
    : null, [detailId, sessions, user])
  const recoveryKey = `${user.id}/${sessionGeneration}`
  if (apiMode && snapshot.sessionAcknowledgementPending) return <SessionAcknowledgementRecovery key={recoveryKey} pending={snapshot.sessionAcknowledgementPending} services={services} />
  if (apiMode && snapshot.sessionSummaryPending) return <SessionSummaryRecovery key={recoveryKey} pending={snapshot.sessionSummaryPending} services={services} />
  if (apiMode && snapshot.sessionOutcomePending) return <SessionOutcomeRecovery key={recoveryKey} pending={snapshot.sessionOutcomePending} services={services} />
  if (apiMode && snapshot.sessionPlanPending) return <SessionPlanRecovery key={recoveryKey} pending={snapshot.sessionPlanPending} services={services} />
  if (apiMode && snapshot.sessionChangePending) return <SessionChangeRecovery key={recoveryKey} pending={snapshot.sessionChangePending} services={services} />
  if (selectedSession) return apiMode
    ? <ApiSessionDetailsRoute key={selectedSession.id} selectedSession={selectedSession} navigate={navigate} openClient={openClient} onChangeSaved={onChangeSaved} />
    : <SessionDetailsRoute key={selectedSession.id} selectedSession={selectedSession} navigate={navigate} openClient={openClient} />
  if (detailId) return <UnavailablePage message="This session is unavailable for your account." />
  return <SessionsPage today={today} user={user} sessions={sessions ?? []} clients={clients} trainers={trainers} onOpen={id => navigate(`sessions/${id}`)} />
}

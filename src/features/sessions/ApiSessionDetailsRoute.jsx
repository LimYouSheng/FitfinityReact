import { useEffect, useState } from 'react'
import usePortalData from '../../hooks/usePortalData.js'
import SessionDetailsPage from './SessionDetailsPage.jsx'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import { managesOperations } from '../../app/permissions.js'

export default function ApiSessionDetailsRoute({ selectedSession, navigate, openClient }) {
  const { snapshot, services, today } = usePortalData()
  const { user, policy, sessionGeneration, serverAt, data } = snapshot
  const [state, setState] = useState(null), [attempt, setAttempt] = useState(0)
  const [limited, setLimited] = useState(null), [clientBusy, setClientBusy] = useState(false), [clientError, setClientError] = useState('')
  const id = selectedSession.id, version = selectedSession.version
  useEffect(() => {
    let current = true
    setState(null)
    services.readSessionDetails({ id }).then(value => {
      if (current) setState({ id, generation: sessionGeneration, value })
    }).catch(error => { if (current) setState({ id, generation: sessionGeneration, error }) })
    return () => { current = false }
  }, [id, version, sessionGeneration, serverAt, services, attempt])
  if (!state || state.id !== id || state.generation !== sessionGeneration) return <p role="status">Loading session…</p>
  if (state.error) return <section role="alert"><p>{state.error.message}</p><button type="button" onClick={() => setAttempt(n => n + 1)}>Retry session</button></section>
  const { session, client, trainer } = state.value
  const fullClient = data.clients.some(c => c.id === client.id)
  const fullTrainer = data.trainers.some(t => t.id === trainer.id)
  const canLimited = !fullClient && !['completed', 'cancelled'].includes(session.status) && client.status === 'active' && state.value.session.packageId && [client.package, ...client.additionalPackages, ...client.packageHistory].some(p => p?.id === session.packageId && p.status === 'active')
  const openLimited = async () => {
    if (clientBusy) return
    setClientBusy(true); setClientError('')
    try { setLimited(await services.readSessionClient({ id, clientId: client.id })) }
    catch (error) { setClientError(error.message) }
    finally { setClientBusy(false) }
  }
  return <><SessionDetailsPage readOnly today={today} policy={policy} user={user} session={session} client={client} trainer={trainer}
    trainers={data.sessionTrainers ?? data.trainers} messages={data.messages ?? []}
    onOpenClient={fullClient ? () => openClient(client.id) : canLimited && !clientBusy ? openLimited : undefined}
    onOpenTrainer={fullTrainer ? () => navigate(managesOperations(user) ? `trainers/${trainer.id}` : 'my-profile') : undefined} />
    {clientError && <p role="alert">{clientError}</p>}
    <ConfirmDialog open={Boolean(canLimited && limited)} title="Session Client" hideConfirm cancelLabel="Close" onCancel={() => setLimited(null)}>
      {limited && <><p>{limited.name}</p><ul>{limited.person_names.map((name, index) => <li key={index}>{name}</li>)}</ul></>}
    </ConfirmDialog>
  </>
}

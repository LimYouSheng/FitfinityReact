import { useEffect, useMemo, useState } from 'react'
import AppShell from './components/AppShell.jsx'
import DashboardPage from './features/dashboard/DashboardPage.jsx'
import ClientsPage from './features/clients/ClientsPage.jsx'
import ClientProfilePage from './features/clients/ClientProfilePage.jsx'
import TrainersPage from './features/trainers/TrainersPage.jsx'
import TrainerProfilePage from './features/trainers/TrainerProfilePage.jsx'
import MigrationPlaceholder from './features/placeholders/MigrationPlaceholder.jsx'
import { clientService } from './services/clientService.js'
import { trainerService } from './services/trainerService.js'
import { mockDb } from './services/mockDb.js'

const routeFromHash = () => location.hash.replace(/^#\/?/, '') || 'dashboard'

export default function App() {
  const [db, setDb] = useState(() => mockDb.read())
  const [userId, setUserId] = useState(() => db.users[0].id)
  const [route, setRoute] = useState(routeFromHash)
  const [selectedClientId, setSelectedClientId] = useState(null)
  const [selectedTrainerId, setSelectedTrainerId] = useState(null)
  const user = db.users.find(item => item.id === userId) ?? db.users[0]

  useEffect(() => {
    const onHash = () => setRoute(routeFromHash())
    addEventListener('hashchange', onHash)
    return () => removeEventListener('hashchange', onHash)
  }, [])

  const navigate = next => { setSelectedClientId(null); setSelectedTrainerId(null); location.hash = `#/${next}`; setRoute(next) }
  const openClient = id => { setSelectedClientId(id); location.hash = '#/clients'; setRoute('clients') }
  const openTrainer = id => { setSelectedTrainerId(id); location.hash = '#/trainers'; setRoute('trainers') }
  const reload = () => setDb(mockDb.read())
  const switchUser = id => { setUserId(id); setSelectedClientId(null); setSelectedTrainerId(null); navigate('dashboard') }
  const reset = () => { mockDb.reset(); reload(); setSelectedClientId(null); setSelectedTrainerId(null); navigate('dashboard') }

  const clients = db.clients
  const trainers = db.trainers
  const selectedClient = useMemo(() => clients.find(item => item.id === selectedClientId), [clients, selectedClientId])
  const selectedTrainer = useMemo(() => trainers.find(item => item.id === selectedTrainerId), [trainers, selectedTrainerId])

  let page
  if (route === 'clients' && selectedClient) {
    page = <ClientProfilePage user={user} client={selectedClient} trainer={trainers.find(t => t.id === selectedClient.trainerId)} onBack={() => setSelectedClientId(null)} onUpdate={async patch => { await clientService.update(selectedClient.id, patch); reload() }} />
  } else if (route === 'clients') {
    page = <ClientsPage user={user} clients={clients} trainers={trainers} onOpen={openClient} />
  } else if (route === 'trainers' && user.role === 'owner' && selectedTrainer) {
    page = <TrainerProfilePage trainer={selectedTrainer} onBack={() => setSelectedTrainerId(null)} onSave={async settings => { await trainerService.updateAutonomy(selectedTrainer.id, settings); reload() }} />
  } else if (route === 'trainers' && user.role === 'owner') {
    page = <TrainersPage trainers={trainers} clients={clients} onOpen={openTrainer} />
  } else if (route === 'dashboard') {
    page = <DashboardPage user={user} clients={clients} trainers={trainers} onRoute={navigate} onOpenClient={openClient} />
  } else {
    const title = ({ requests: user.role === 'owner' ? 'Requests' : 'My Requests', sessions: 'Sessions', remuneration: 'Remuneration', exercises: 'Exercise Library', content: 'Website Content' })[route] ?? 'Dashboard'
    page = <MigrationPlaceholder title={title} />
  }

  return <AppShell user={user} users={db.users} userId={userId} route={route} onRoute={navigate} onUserChange={switchUser} onReset={reset}>{page}</AppShell>
}

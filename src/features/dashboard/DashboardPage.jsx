import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'

export default function DashboardPage({ user, clients, trainers, onRoute, onOpenClient }) {
  const visibleClients = user.role === 'owner' ? clients : clients.filter(client => client.trainerId === user.trainerId)
  return (
    <>
      <div className="page-head"><div><span className="eyebrow">Staff portal</span><h1>Dashboard</h1><p>{user.role === 'owner' ? 'Owner operational overview' : 'Your assigned-client overview'}</p></div><StatusBadge tone="blue">React M1</StatusBadge></div>
      <div className="stats-grid">
        <Panel><span>Visible clients</span><strong>{visibleClients.length}</strong></Panel>
        <Panel><span>{user.role === 'owner' ? 'Trainers' : 'Role'}</span><strong>{user.role === 'owner' ? trainers.length : 'Trainer'}</strong></Panel>
        <Panel><span>Mock persistence</span><strong>On</strong></Panel>
      </div>
      <Panel>
        <div className="section-head"><div><h2>Migration checkpoint</h2><p>The shell, permissions, client overview and trainer autonomy are now React-owned.</p></div></div>
        <div className="checkpoint-grid">
          <button type="button" onClick={() => onRoute('clients')}><strong>Clients</strong><span>Open migrated client flows</span></button>
          {user.role === 'owner' && <button type="button" onClick={() => onRoute('trainers')}><strong>Trainers</strong><span>Test approval-needed semantics</span></button>}
          {visibleClients[0] && <button type="button" onClick={() => onOpenClient(visibleClients[0].id)}><strong>Reference profile</strong><span>Compare v0.57 section order</span></button>}
        </div>
      </Panel>
    </>
  )
}

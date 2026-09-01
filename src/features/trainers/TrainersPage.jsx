import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'

export default function TrainersPage({ trainers, clients, onOpen }) {
  return (
    <>
      <div className="page-head"><div><span className="eyebrow">Trainers</span><h1>All Trainers</h1><p>Owner view of staff and approval settings</p></div></div>
      <Panel><div className="table-wrap"><table><thead><tr><th>Trainer</th><th>Specialty</th><th>Assigned Clients</th><th>Autonomy</th><th></th></tr></thead><tbody>
        {trainers.map(trainer => {
          const supervised = Object.values(trainer.approvalNeeded).filter(Boolean).length
          return <tr key={trainer.id}><td><strong>{trainer.name}</strong><br/><small>{trainer.email}</small></td><td>{trainer.specialty}</td><td>{clients.filter(client => client.trainerId === trainer.id).length}</td><td><StatusBadge tone={supervised === 0 ? 'green' : supervised === 4 ? 'amber' : 'blue'}>{supervised === 0 ? 'Direct allowed' : supervised === 4 ? 'Approval needed' : 'Mixed'}</StatusBadge></td><td><button type="button" className="btn small" onClick={() => onOpen(trainer.id)}>View</button></td></tr>
        })}
      </tbody></table></div></Panel>
    </>
  )
}

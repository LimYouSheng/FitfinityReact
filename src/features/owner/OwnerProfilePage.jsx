import Panel from '../../components/Panel.jsx'
import ProfileAvatar from '../../components/ProfileAvatar.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'

export default function OwnerProfilePage({ user }) {
  return <>
    <div className="page-head profile-identity-card">
      <div className="profile-identity-main">
        <ProfileAvatar name={user.name} />
        <div><span className="eyebrow">Owner Profile</span><h1>{user.name}</h1></div>
      </div>
      <div className="profile-card-statuses" aria-label="Account status">
        <StatusBadge tone={user.status === 'inactive' ? 'amber' : 'green'}>
          {user.status === 'inactive' ? 'Inactive' : 'Active'}
        </StatusBadge>
      </div>
    </div>
    <Panel>
      <div className="section-head"><h2>Account Details</h2></div>
      <div className="info-list profile-info-grid">
        <div className="info-row"><span>Name</span><strong>{user.name}</strong></div>
        <div className="info-row"><span>Role</span><strong>Owner / Site Admin</strong></div>
      </div>
    </Panel>
  </>
}

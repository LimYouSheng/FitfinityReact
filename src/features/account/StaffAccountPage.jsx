import { managesOperations, staffRoleLabel } from '../../app/permissions.js'
import { phoneText } from '../../app/contact.js'
import { formatDate } from '../../utils/date.js'
import Panel from '../../components/Panel.jsx'
import ProfileAvatar from '../../components/ProfileAvatar.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'

// Presentation only: App owns account-scoped routes, Back/swipe and session lifecycle.
export default function StaffAccountPage({ user, profile = false, readOnly = true, onNavigate, onSignOut, busy }) {
  if (profile && user.role === 'admin') return <>
    <div className="page-head profile-identity-card">
      <div className="profile-identity-main">
        <ProfileAvatar name={user.name} />
        <div><span className="eyebrow">Admin</span><h1>{user.name}</h1></div>
      </div>
      <div className="profile-card-statuses" aria-label="Admin status">
        <StatusBadge tone={user.status === 'inactive' ? 'amber' : 'green'}>
          {user.status === 'inactive' ? 'Inactive' : 'Active'}
        </StatusBadge>
      </div>
    </div>
    <Panel>
      <div className="section-head"><h2>General Information</h2></div>
      <div className="info-list profile-info-grid">
        {[
          ['Staff name', user.name], ['Mobile Number', typeof user.phone === 'string' ? user.phone : phoneText(user.phone)],
          ['Email', user.email], ['Birthday', formatDate(user.birthday)],
          ['Gender', user.gender], ['Role', staffRoleLabel(user)],
        ].map(([label, value]) => <div className="info-row" key={label}><span>{label}</span><strong>{value || '—'}</strong></div>)}
      </div>
    </Panel>
  </>
  return <Panel>
    <span className="eyebrow">Staff portal</span><h1>Your account</h1>
    <dl><dt>Name</dt><dd>{user.name}</dd><dt>Email</dt><dd>{user.email}</dd><dt>Role</dt><dd>{staffRoleLabel(user)}</dd></dl>
    {readOnly && <p className="helper">Client, trainer and package information is available to view. Changes and other workflows will be available in a later release.</p>}
    <div className="inline-actions"><button className="secondary-button" onClick={() => onNavigate('clients')}>View Clients</button>
      {managesOperations(user) && <><button className="secondary-button" onClick={() => onNavigate('trainers')}>View Trainers</button><button className="secondary-button" onClick={() => onNavigate('packages')}>View Packages</button></>}
      <button className="secondary-button" onClick={() => onNavigate('change-password')}>Change Password</button><button className="primary-button" disabled={busy} onClick={onSignOut}>Sign Out</button></div>
  </Panel>
}

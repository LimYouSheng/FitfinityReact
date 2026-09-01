export default function RoleSwitcher({ users, userId, onChange }) {
  return (
    <label className="role-switcher">
      <span>Mock identity</span>
      <select value={userId} onChange={event => onChange(event.target.value)}>
        {users.map(user => <option key={user.id} value={user.id}>{user.name} — {user.role === 'owner' ? 'Owner' : user.profile}</option>)}
      </select>
    </label>
  )
}

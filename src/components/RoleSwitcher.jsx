export default function RoleSwitcher({ users, userId, onChange }) {
  const selectable = users.filter(user => (user.status ?? 'active') === 'active')

  return (
    <label className="role-switcher">
      <span>Demo identity</span>
      <select value={userId} onChange={event => onChange(event.target.value)}>
        {selectable.map(user => (
          <option key={user.id} value={user.id}>
            {user.name} — {user.role === 'owner' ? 'Owner' : user.profile}
          </option>
        ))}
      </select>
    </label>
  )
}

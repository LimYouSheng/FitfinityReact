import { useState } from 'react'
import Panel from '../../components/Panel.jsx'
import SelectField from '../../components/SelectField.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePageState from '../../hooks/usePageState.js'
import usePagination from '../../hooks/usePagination.js'
import { GENDERS } from '../../app/contact.js'

/** Owner-only directory: preserve navigation filters without storing editable staff data. */
export default function AdminDirectory({ records, onNavigate, onCreate }) {
  const [query, setQuery] = usePageState('AdminDirectory.query', '')
  const [status, setStatus] = usePageState('AdminDirectory.status', 'all')
  const [gender, setGender] = usePageState('AdminDirectory.gender', '')
  const [searchOpen, setSearchOpen] = useState(false)
  const matches = record => `${record.details.name} ${record.details.email}`.toLowerCase().includes(query.trim().toLowerCase())
  const suggestions = query.trim() ? records.filter(matches).slice(0, 6) : []
  const visible = records.filter(record => matches(record) && (status === 'all' || record.status === status) && (!gender || record.details.gender === gender))
  const pagination = usePagination(visible, `${query}|${status}|${gender}`, 'AdminDirectory.page')
  return <>
    <div className="page-head directory-page-head"><div><span className="eyebrow">System</span><h1>Admin</h1></div>
      <button type="button" className="onboarding-button primary" onClick={onCreate}>Create Admin</button>
    </div>
    <Panel>
      <div className="list-controls admin-controls">
        <div className="search-suggest-wrap" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setSearchOpen(false) }}>
          <input aria-label="Search admin" aria-autocomplete="list" autoComplete="off" placeholder="Search admin or email" value={query}
            onFocus={() => setSearchOpen(true)} onChange={event => { setQuery(event.target.value); setSearchOpen(true) }} />
          {searchOpen && suggestions.length > 0 && <div className="search-suggestions" role="listbox" aria-label="Admin search suggestions">
            {suggestions.map(record => <button key={record.id} type="button" role="option" onMouseDown={event => event.preventDefault()}
              onClick={() => { setQuery(record.details.name); setSearchOpen(false) }}><strong>{record.details.name}</strong><span>{record.details.email}{record.status === 'inactive' ? ' • Inactive' : ''}</span></button>)}
          </div>}
        </div>
        <SelectField aria-label="Filter admins by status" value={status} onChange={event => setStatus(event.target.value)}>
          <option value="all">All status</option><option value="active">Active</option><option value="inactive">Inactive</option>
        </SelectField>
        <SelectField aria-label="Filter admins by gender" value={gender} onChange={event => setGender(event.target.value)}>
          <option value="">All genders</option>{GENDERS.map(value => <option key={value}>{value}</option>)}
        </SelectField>
      </div>
      <div className="compact-list" aria-label="Admin list">
        <div className="compact-list-head trainer-compact-grid"><span>Admin</span><span>Email</span><span>View</span></div>
        {pagination.items.map(record => <div className={`compact-list-row trainer-compact-grid ${record.status === 'inactive' ? 'inactive-row' : ''}`.trim()} key={record.id}>
          <div className="compact-name-wrap"><strong className="compact-primary">{record.details.name}</strong>{record.status === 'inactive' && <span className="inline-inactive">Inactive</span>}</div>
          <span className="compact-secondary">{record.details.email}</span>
          <button type="button" className="secondary-button small compact-view" aria-label={`View ${record.details.name}`} onClick={() => onNavigate(`admins/${record.id}`)}>View</button>
        </div>)}
        {!visible.length && <div className="empty">No matching admins.</div>}
      </div>
      <PaginationControls {...pagination} onPage={pagination.setPage} />
    </Panel>
  </>
}

import { pastClientPackages, progressForPackage } from '../../app/clientPackages.js'
import { clientProgressExercises, progressSessionSummary } from '../../app/progress.js'
import { useMemo } from 'react'
import { formatDate } from '../../utils/date.js'
import Panel from '../../components/Panel.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import StrengthProgress from './StrengthProgress.jsx'

export default function PackageProgress({ client, sessions = [], user, packageId, onOpenPackage, ...props }) {
  const reportClient = useMemo(() => ({ ...client, strengthProgress: clientProgressExercises(client, sessions) }), [client, sessions])
  const packages = [ ...(client.package.status === 'inactive' ? [] : [client.package]), ...pastClientPackages(client) ]
    .sort((a, b) => b.startDate.localeCompare(a.startDate) || a.id.localeCompare(b.id))
  const pages = usePagination(packages, client.id, `client.${client.id}.progressPackagesPage`)
  const kind = purchased => purchased.id === client.package.id && purchased.status !== 'inactive' ? 'Current' : 'Past'
  if (packageId) {
    const purchased = packages.find(item => item.id === packageId)
    if (!purchased) return <Panel><p className="empty">This package is unavailable.</p></Panel>
    const scopedClient = { ...reportClient, reportPackageId: packageId, strengthProgress: progressForPackage(reportClient, packageId) }
    const summary = progressSessionSummary(reportClient, sessions, packageId)
    return <div className="stack-gap">
      <div className="section-head"><div><h2>{kind(purchased)} · {purchased.name ?? `${purchased.total} Sessions`}</h2>
        <p>{formatDate(purchased.startDate)} – {formatDate(purchased.endDate)}{purchased.status === 'inactive' ? ' · Inactive' : ''}</p>
        <p aria-label="Package progress summary">Completed: {summary.completed} · With exercise records: {summary.recorded}</p>
      </div></div>
      <StrengthProgress key={packageId} client={scopedClient} user={user} {...props} />
    </div>
  }
  return <Panel>
    <div className="section-head"><h2>Progress Packages</h2></div>
    <div className="package-progress-list" aria-label="Progress packages">
      <div className="package-progress-head" aria-hidden="true"><span>Package</span><span>Dates</span><span>Completed</span><span /></div>
      {pages.items.map(purchased => <article className="package-progress-row" key={purchased.id} data-package-id={purchased.id}>
        <div><strong>{purchased.name ?? `${purchased.total} Sessions`}</strong><span>{kind(purchased)}{purchased.status === 'inactive' ? ' · Inactive' : ''}</span></div>
        <span>{formatDate(purchased.startDate)} – {formatDate(purchased.endDate)}</span>
        <span>{progressSessionSummary(client, sessions, purchased.id).completed} / {purchased.total}</span>
        <button type="button" className="btn small" onClick={() => onOpenPackage(purchased.id)}>View</button>
      </article>)}
      {!packages.length && <p className="empty">No packages yet.</p>}
    </div>
    <PaginationControls {...pages} onPage={pages.setPage} />
  </Panel>
}

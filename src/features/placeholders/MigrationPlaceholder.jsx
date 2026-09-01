import Panel from '../../components/Panel.jsx'

export default function MigrationPlaceholder({ title }) {
  return <><div className="page-head"><div><span className="eyebrow">Next migration slice</span><h1>{title}</h1><p>This route is wired into the canonical shell but its v0.57 behaviour has not been reconstructed yet.</p></div></div><Panel><h2>Why it is intentionally not copied yet</h2><p className="body-copy">We will migrate this feature from final behaviour into owned React components and services, then add regression tests before moving to the next domain. No legacy patch scripts are loaded here.</p></Panel></>
}

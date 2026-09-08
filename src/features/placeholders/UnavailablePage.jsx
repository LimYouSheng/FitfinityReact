import Panel from '../../components/Panel.jsx'

export default function UnavailablePage({ title = 'Page unavailable', message = 'This page is unavailable.' }) {
  return <>
    <div className="page-head"><h1>{title}</h1></div>
    <Panel><p className="body-copy">{message}</p></Panel>
  </>
}

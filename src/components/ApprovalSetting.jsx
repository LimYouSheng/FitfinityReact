export default function ApprovalSetting({ label, checked, disabled = false, onChange }) {
  return (
    <label className="approval-setting">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={event => onChange?.(event.target.checked)} />
      <span>{label}</span>
    </label>
  )
}

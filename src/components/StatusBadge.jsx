export default function StatusBadge({ tone = 'neutral', className = '', children }) {
  return <span className={`status-badge ${tone} ${className}`.trim()}>{children}</span>
}

export default function Panel({ className = '', children }) {
  return <section className={`panel ${className}`.trim()}>{children}</section>
}

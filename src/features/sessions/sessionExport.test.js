import { describe, expect, it } from 'vitest'
import { sessionSummaryText, sessionSummaryPages } from './sessionExport.jsx'

describe('session summary export', () => {
  it('includes selected captions and authoritative package dates, paginates long Unicode text and excludes unselected content', () => {
    const client = { name: '陈 & Amanda', package: { id: 'purchase', name: '12 Sessions', total: 12, startDate: '2026-08-01', endDate: '2026-10-29' } }
    const session = { date: '2026-09-02', from: '18:00', to: '19:00', sessionNumber: 6, packageId: 'purchase', packageTotal: 999 }
    const videos = [{ name: 'Romanian Deadlift', weight: '40 kg', reps: '8', rounds: '2', rest: '60 sec' }]
    const text = sessionSummaryText(client, session, 'Strong session.', videos)
    expect(text).toContain('• Romanian Deadlift — 40 kg · 8 reps · 2 rounds · 1 minute rest interval')
    expect(text).toContain('Session 6 / 12')
    expect(text).toContain('01 Aug 2026 – 29 Oct 2026')
    expect(text).not.toContain('999')
    const withoutSummary = sessionSummaryText(client, session, '', videos)
    expect(withoutSummary).not.toContain('Client-Facing Summary')
    expect(withoutSummary).toContain('Selected video captions (1)')
    const pages = sessionSummaryPages({ client, session, summary: Array.from({ length: 90 }, (_, i) => `Row ${i} <script>not markup</script>`).join('\n'), videos: [] })
    expect(pages.length).toBeGreaterThan(1)
    const documents = pages.map(page => new DOMParser().parseFromString(page.svg, 'image/svg+xml'))
    const content = documents.map(doc => doc.documentElement.textContent).join(' ')
    expect(content).toContain('陈 & Amanda')
    expect(content).toContain('Row 89 <script>not markup</script>')
    expect(content).not.toContain('Romanian Deadlift')
    for (const doc of documents) {
      expect(doc.querySelector('script, parsererror')).toBeNull()
      expect([...doc.querySelectorAll('text')].every(node => Number(node.getAttribute('y')) <= 1370)).toBe(true)
    }
  })
})

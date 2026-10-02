export function automaticClientSummary(session, outcome) {
  const items = session.exercisePlan ?? []
  const lines = [
    `Session duration: ${outcome.durationMinutes} minutes`,
    `Exercises completed (${items.length}).`,
  ]

  items.forEach(item => {
    const details = [
      item.weight,
      item.reps && `${item.reps} reps`,
      item.rounds && `${item.rounds} rounds`,
      item.rest && `${item.rest} rest`,
      ...(item.customDetails ?? []).map(detail => typeof detail === 'string' ? detail : detail.value).filter(Boolean),
    ].filter(Boolean).join(' · ')

    lines.push(`- ${item.name}${details ? ` — ${details}` : ''}`)
  })

  return lines.join('\n')
}


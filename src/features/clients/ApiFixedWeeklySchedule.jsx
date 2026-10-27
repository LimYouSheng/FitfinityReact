import useReviewLifetime from '../../hooks/useReviewLifetime.js'
import { useEffect, useRef, useState } from 'react'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import FixedWeeklySchedule from './FixedWeeklySchedule.jsx'

export default function ApiFixedWeeklySchedule({ client, workflow, editable, editing, disabled, onEditing }) {
  const { activeEdit } = useEditGuard()
  const beginReview = useReviewLifetime(disabled || !editable, `${client.id}/${client.status}`)
  const [draft, setDraft] = useState(null)
  const [saved, setSaved] = useState(false)
  const finishing = useRef(false)
  useEffect(() => {
    if (saved && !activeEdit && !finishing.current) {
      finishing.current = true
      void workflow.saved().then(snapshot => {
        if (snapshot) { finishing.current = false; setSaved(false); setDraft(null) }
      }).catch(() => {})
    }
  }, [saved, activeEdit, workflow])
  return <FixedWeeklySchedule slots={client.fixedWeeklySchedule} editable={editable && !saved}
    editing={editing} editDisabled={disabled} uncertain={draft?.uncertain}
    onBeginEdit={async () => {
      const isCurrent = beginReview()
      try {
        const current = await workflow.review()
        if (!isCurrent()) return
        setDraft(current); onEditing(true)
        return { slots: current.slots }
      } catch (error) { if (isCurrent()) throw error }
    }} onEndEdit={() => onEditing(false)}
    onReviewSave={async slots => {
      const preview = await workflow.preview({ reviewed: draft.reviewed, slots })
      return preview.outcome === 'requested' ? `Send these weekly times for owner approval. ${preview.updatedSessions} eligible upcoming sessions would change after approval; approved times remain unchanged now.` : `Update these weekly times and ${preview.updatedSessions} eligible upcoming sessions. Dates and purchased terms stay unchanged.`
    }} onSave={async slots => {
      try {
        const result = await workflow.save({ reviewed: draft.reviewed, slots })
        setSaved(true)
        return result
      } catch (failure) {
        setDraft(current => ({ ...current, slots, uncertain: !(failure.status >= 400 && failure.status < 500) }))
        throw failure
      }
    }} />
}

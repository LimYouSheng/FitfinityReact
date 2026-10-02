import ClientAssessments from './ClientAssessments.jsx'
import ClientGeneralInformation from './ClientGeneralInformation.jsx'
import ClientEditableText from './ClientEditableText.jsx'
import { clientProfileDraft } from '../../app/clientOnboarding.js'
import ClientReactivationDialog from './ClientReactivationDialog.jsx'
import ReassignTrainerDialog from './ReassignTrainerDialog.jsx'
import usePageState from '../../hooks/usePageState.js'
import { useEffect, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import ProfileAvatar from '../../components/ProfileAvatar.jsx'
import ProfileNavigation from '../../components/ProfileNavigation.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import FixedWeeklySchedule from './FixedWeeklySchedule.jsx'
import ClientProfileTabs from './ClientProfileTabs.jsx'
import { managesOperations, canEditClientCoachingNotes, canEditClientGeneral } from '../../app/permissions.js'

export default function ClientProfilePage({
  user,
  readOnly = false,
  assessmentsAvailable = true,
  sessionViewsAvailable = true,
  client,
  clients,
  trainer,
  trainers,
  sessions,
  today,
  onOpenSession,
  progressRoute = false,
  progressPackageId,
  onOpenProgressPackage,
  onSelectProfileTab,
  onUpdate,
  onSaveAssessment,
  timeZone,
  onRecordProgressReport,
  onLoadProgressReportHistory,
  onSaveFixedWeeklySchedule,
  onReassignTrainer,
  onDeactivate,
  onReactivate,
  packages,
  policy,
  onRenewPackage,
  onDeactivatePackage,
  onDeletePackageSessions,
  packageCreditTransactions,
}) {
  const { guardNavigation, setActiveEdit } = useEditGuard()
  const [savedTab, setTab] = usePageState(`client.${client.id}.tab`, 'overview')
  const requestedTab = progressRoute ? 'progress' : savedTab
  const tab = !sessionViewsAvailable && !['overview', 'package'].includes(requestedTab) ? 'overview' : requestedTab
  const [activeEditor, setActiveEditor] = useState(null)
  const [assessmentPerson, setAssessmentPerson] = useState(0)
  const [deactivateOpen, setDeactivateOpen] = useState(false)

  useEffect(() => { setActiveEditor(null) }, [client.id, client.status])

  useEffect(() => {
    const label = ({ reactivation: 'Client reactivation', general: 'Client information', trainer: 'Trainer reassignment', schedule: 'Fixed weekly schedule', health: 'Health notes', remarks: 'Client remarks', assessment: 'Client assessment' })[activeEditor] ?? null
    setActiveEdit(label)
    return () => setActiveEdit(null)
  }, [activeEditor, setActiveEdit])

  const ownerEditable = !readOnly && canEditClientGeneral(user, client)
  const notesEditable = !readOnly && canEditClientCoachingNotes(user, client)

  const assignedTrainerEditable =
    user.role === 'trainer' &&
    user.trainerId === client.trainerId &&
    client.status !== 'inactive'

  const scheduleEditable =
    !readOnly && client.status !== 'inactive' && (managesOperations(user) || assignedTrainerEditable)


  return (
    <>
      <div className="page-head profile-identity-card">
        <div className="profile-identity-main">
          <ProfileAvatar name={client.name} />

          <div>
            <span className="eyebrow">Client</span>
            <h1>{client.name}</h1>
          </div>
        </div>

        <div className="profile-card-statuses" aria-label="Client status">
          <StatusBadge tone={client.status === 'inactive' ? 'amber' : 'green'}>
            {client.status === 'inactive' ? 'Inactive' : 'Active'}
          </StatusBadge>
        </div>
      </div>

      <ProfileNavigation
        items={[
            ['overview', 'Overview'],
            ['package', 'Package'],
            ...(sessionViewsAvailable ? [['history', 'Session History'], ['upcoming', 'Upcoming Sessions'], ['progress', 'Progress']] : []),
        ]}
        activeKey={tab}
        onSelect={key => guardNavigation(() => {
          setActiveEditor(null)
          setTab(key)
          onSelectProfileTab?.(key)
        })}
      >

          {!readOnly && managesOperations(user) && client.status !== 'inactive' && (
            <button
              type="button"
              className="profile-menu-danger"
              disabled={Boolean(activeEditor)}
              onClick={() => setDeactivateOpen(true)}
            >
              Deactivate Client
            </button>
          )}

          {!readOnly && managesOperations(user) && client.status === 'inactive' && (
            <button
              type="button"
              className="profile-menu-reactivate"
              disabled={Boolean(activeEditor)}
              onClick={() => setActiveEditor('reactivation')}
            >
              Reactivate Client
            </button>
          )}
      </ProfileNavigation>

      {activeEditor === 'reactivation' && !readOnly && managesOperations(user) && client.status === 'inactive' &&
        <ClientReactivationDialog client={client} clients={clients} trainers={trainers} sessions={sessions}
          packageCreditTransactions={packageCreditTransactions} onSave={onReactivate} onClose={() => setActiveEditor(null)} />}

      {activeEditor === 'trainer' && ownerEditable && <ReassignTrainerDialog client={client} trainers={trainers} sessions={sessions}
        packageCreditTransactions={packageCreditTransactions} timeZone={timeZone} onSave={onReassignTrainer} onClose={() => setActiveEditor(null)} />}

      {tab === 'overview' && <>
      <div className="profile-overview-stack">
        <ClientGeneralInformation client={client} trainer={trainer} policy={policy}
          ownerEditable={ownerEditable} activeEditor={activeEditor} setActiveEditor={setActiveEditor} onUpdate={onUpdate} />

        <FixedWeeklySchedule
          slots={client.fixedWeeklySchedule}
          editable={scheduleEditable}
          editing={activeEditor === 'schedule'}
          editDisabled={Boolean(activeEditor)}
          onBeginEdit={() => setActiveEditor('schedule')}
          onEndEdit={() => setActiveEditor(null)}
          onSave={onSaveFixedWeeklySchedule}
        />
      </div>

      <div className="stack-gap">
        {assessmentsAvailable && <Panel>
          <div className="section-head"><h2>Health & Assessments</h2></div>
          <ClientAssessments people={clientProfileDraft(client, policy).people} activePerson={assessmentPerson}
            setActivePerson={setAssessmentPerson} readOnly fillUnfilled={ownerEditable && Boolean(onSaveAssessment)}
            disabled={Boolean(activeEditor) && activeEditor !== 'assessment'} assessor={user.name} timeZone={timeZone}
            onEditChange={editing => setActiveEditor(editing ? 'assessment' : null)}
            onSaveForm={(personIndex, formId, record) => {
              const person = clientProfileDraft(client, policy).people[personIndex]
              return onSaveAssessment({ personIndex, formId, record, expectedPerson: { name: person.name, birthday: person.birthday } })
            }} />
        </Panel>}
        {client.healthNotes && <ClientEditableText
          title="Health / Limitation Notes"
          value={client.healthNotes}
          editable={notesEditable}
          multiline
          editing={activeEditor === 'health'}
          editDisabled={Boolean(activeEditor)}
          onBeginEdit={() => setActiveEditor('health')}
          onEndEdit={() => setActiveEditor(null)}
          onSave={healthNotes => onUpdate({ healthNotes })}
        />}

        <ClientEditableText
          title="Remarks"
          value={client.remarks}
          editable={notesEditable}
          multiline
          editing={activeEditor === 'remarks'}
          editDisabled={Boolean(activeEditor)}
          onBeginEdit={() => setActiveEditor('remarks')}
          onEndEdit={() => setActiveEditor(null)}
          onSave={remarks => onUpdate({ remarks })}
        />
      </div>
      </>}

      {tab !== 'overview' && (
        <ClientProfileTabs
          clients={clients}
          readOnly={readOnly}
          progressPackageId={progressPackageId}
          onOpenProgressPackage={onOpenProgressPackage}
          packages={packages}
          policy={policy}
          onRenewPackage={onRenewPackage}
          onDeactivatePackage={onDeactivatePackage}
          onDeletePackageSessions={onDeletePackageSessions}
          packageCreditTransactions={packageCreditTransactions}
          tab={tab}
          user={user}
          timeZone={timeZone}
          onRecordProgressReport={onRecordProgressReport}
          onLoadProgressReportHistory={onLoadProgressReportHistory}
          client={client}
          sessions={sessions}
          today={today}
          trainers={trainers}
          onOpenSession={onOpenSession}
        />
      )}

      <ConfirmDialog
        open={deactivateOpen}
        title={`Deactivate ${client.name}?`}
        confirmLabel="Deactivate Client"
        danger
        onCancel={() => setDeactivateOpen(false)}
        onConfirm={async () => {
          try {
            await onDeactivate()
            setDeactivateOpen(false)
          } catch { /* Failure is shown in the action banner; keep the dialog open. */ }
        }}
      >
        <p>
          The client will become inactive, move to the bottom of Clients,
          and remain visible to the assigned trainer. All packages are deactivated. Client information and sessions become read-only.
        </p>
      </ConfirmDialog>
    </>
  )
}

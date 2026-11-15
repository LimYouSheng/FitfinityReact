import fs from 'node:fs'
import path from 'node:path'
import { parse } from 'yaml'

const fail = message => { throw new Error(`Quality setup: ${message}`) }
const equal = (left, right) => JSON.stringify(left) === JSON.stringify(right)
const requireGate = (job, command) => {
  const steps = (job?.steps ?? []).filter(step => (step.run ?? '').split('\n').some(line => line.trim() === command || line.trim().startsWith(`${command} `)))
  if (steps.length !== 1) fail(`expected exactly one required command: ${command}`)
  const step = steps[0]
  if (step.if != null || step['continue-on-error'] || /\|\|\s*(true|:)|set\s+\+e/.test(step.run)) fail(`optional or suppressed gate: ${command}`)
  if (step.run.includes('|') && !step.run.includes('set -euo pipefail')) fail(`missing pipeline failure propagation: ${command}`)
}

export function readQualitySetup(root = process.cwd()) {
  const read = file => fs.readFileSync(path.join(root, file), 'utf8')
  return {
    dependabot: parse(read('.github/dependabot.yml')),
    pages: parse(read('.github/workflows/pages.yml')),
    verify: parse(read('.github/workflows/verify.yml')),
    infrastructure: parse(read('.github/workflows/infrastructure.yml')),
    image: parse(read('.github/workflows/aws-image.yml')),
    acceptance: parse(read('.github/workflows/aws-image-accept.yml')),
    preparation: parse(read('.github/workflows/aws-release-prepare.yml')),
    observation: parse(read('.github/workflows/aws-release-observe.yml')),
    schemaProbe: parse(read('.github/workflows/aws-schema-probe.yml')),
    schemaUpgrade: parse(read('.github/workflows/aws-schema-upgrade.yml')),
    maintenance: parse(read('.github/workflows/aws-maintenance.yml')),
    packageJson: JSON.parse(read('package.json')),
    lock: JSON.parse(read('package-lock.json')),
  }
}

export function verifyQualitySetup({ dependabot, pages, verify, infrastructure, image, acceptance, preparation, observation, schemaProbe, schemaUpgrade, maintenance, packageJson, lock }) {
  for (const workflow of [image, preparation, observation, schemaProbe, schemaUpgrade, maintenance]) {
    if (workflow.env?.FITFINITY_DEPLOYMENT_TARGETS_JSON !== '${{ vars.FITFINITY_DEPLOYMENT_TARGETS_JSON }}') fail('deployment target configuration must come from repository variables')
  }
  for (const event of ['pull_request', 'push']) {
    if (!equal(pages.on?.[event]?.branches, ['main']) || Object.keys(pages.on[event]).some(key => key !== 'branches')) fail(`${event} must run all gates for main without path filtering`)
  }
  if (Object.hasOwn(pages.on, 'pull_request_target')) fail('PR checks must use pull_request')
  if (!equal(preparation.permissions, { contents: 'read' }) || Object.hasOwn(preparation.on, 'pull_request_target')) fail('release preparation must be credential-free')
  if (!equal(Object.keys(preparation.jobs).sort(), ['frontend-and-schema', 'runtime-build'])) fail('release preparation jobs differ')
  for (const job of Object.values(preparation.jobs)) {
    if (job.needs || job.if || job.environment || job.secrets || job.permissions || job['continue-on-error'] || job['timeout-minutes'] > 60) fail('release preparation must run concurrently without deployment authority')
    for (const step of job.steps) {
      if (step.uses && !/^actions\/(checkout|setup-node|upload-artifact)@[0-9a-f]{40}$/.test(step.uses)) fail('unexpected action in credential-free release preparation')
      if (/secrets\.|id-token|configure-aws-credentials|docker push|deploy\.py/.test(JSON.stringify(step))) fail('release preparation must not deploy or receive credentials')
      if (step.uses?.startsWith('actions/checkout@') && step.with?.['persist-credentials'] !== false) fail('release preparation must not persist credentials')
      if (step.uses?.startsWith('actions/upload-artifact@') && step.if !== 'always()') fail('release preparation must retain failures')
    }
  }
  const probe = preparation.jobs['frontend-and-schema'].steps.find(step => step.name === 'Prepare optional private schema probe review')
  if (probe?.if !== "github.event_name == 'workflow_dispatch' && inputs.probe_bindings != ''" || probe?.env?.PROBE_BINDINGS !== '${{ inputs.probe_bindings }}' || !probe.run.includes('--source-sha "$GITHUB_SHA" --profile "$DEPLOYMENT_PROFILE"') || probe?.env?.DEPLOYMENT_PROFILE !== '${{ steps.target.outputs.profile }}' || probe.run.includes('${{')) fail('probe review must bind exact source and pass metadata through environment')
  requireGate(preparation.jobs['frontend-and-schema'], 'python3 backend/infrastructure/deployment_profile.py')
  const prepareTarget = preparation.jobs['frontend-and-schema'].steps.find(step => step.id === 'target')
  if (prepareTarget?.env?.DEPLOYMENT_TARGET !== "${{ inputs.target || vars.DEPLOYMENT_TARGET || 'developer' }}" || prepareTarget.run.includes('${{')) fail('release preparation target selection differs')
  requireGate(preparation.jobs['frontend-and-schema'], 'python3 backend/infrastructure/release_readiness.py')
  requireGate(preparation.jobs['runtime-build'], 'docker build --pull --platform linux/amd64 --target runtime')
  const upgrade = schemaUpgrade.jobs?.upgrade
  if (!equal(Object.keys(schemaUpgrade.on), ['workflow_dispatch']) || !equal(schemaUpgrade.permissions, { contents: 'read' }) || !equal(upgrade?.needs, ['offline', 'target']) || upgrade?.environment !== '${{ needs.target.outputs.environment }}' || upgrade?.if !== "github.ref == 'refs/heads/main' && vars.AWS_SCHEMA_UPGRADE_ENABLED == 'true'") fail('schema upgrade must be manual, main-only, disabled by default and protected')
  if (!equal(upgrade.concurrency, { group: 'fitfinity-${{ needs.target.outputs.environment }}', 'cancel-in-progress': false }) || !equal(upgrade.permissions, { contents: 'read', actions: 'read', 'id-token': 'write' }) || schemaUpgrade.jobs.offline.uses !== './.github/workflows/infrastructure.yml') fail('schema upgrade concurrency, verification or permissions differ')
  const upgradeAuth = upgrade.steps.findIndex(step => step.uses?.startsWith('aws-actions/configure-aws-credentials@'))
  const upgradeEvidence = upgrade.steps.findIndex(step => step.run === 'python3 backend/infrastructure/schema_upgrade_artifacts.py')
  if (upgradeEvidence < 0 || upgradeAuth <= upgradeEvidence) fail('upgrade evidence must precede AWS credentials')
  const credentials = upgrade.steps[upgradeAuth].with
  if (credentials['role-to-assume'] !== '${{ vars.AWS_SCHEMA_UPGRADE_ROLE_ARN }}' || credentials['allowed-account-ids'] !== '${{ needs.target.outputs.account }}' || credentials['aws-region'] !== '${{ needs.target.outputs.region }}' || credentials['unset-current-credentials'] !== true) fail('upgrade credential target differs')
  if (schemaUpgrade.jobs.target.outputs.role !== '${{ steps.target.outputs.upgrade_role }}') fail('upgrade must use its separate target role')
  const roleCheck = upgrade.steps.find(step => step.run === 'test "$UPGRADE_ROLE" = "$EXPECTED_ROLE"')
  if (roleCheck?.env?.UPGRADE_ROLE !== '${{ vars.AWS_SCHEMA_UPGRADE_ROLE_ARN }}' || roleCheck?.env?.EXPECTED_ROLE !== '${{ needs.target.outputs.role }}') fail('upgrade role comparison missing')
  const upgradeReceipt = upgrade.steps.find(step => step.uses?.startsWith('actions/upload-artifact@'))
  if (upgradeReceipt?.if !== 'always()' || upgradeReceipt?.with?.path !== '${{ runner.temp }}/schema-upgrade-receipt.json') fail('upgrade must retain failed and uncertain receipts')
  for (const step of upgrade.steps) {
    if (step['continue-on-error'] || (step.run ?? '').includes('${{ inputs.')) fail('upgrade must not interpolate input into shell or suppress errors')
  }
  const maintenanceJob = maintenance.jobs?.maintenance
  if (!equal(maintenance.on?.workflow_dispatch?.inputs?.mode?.options, ['pause', 'inspect', 'record-pause-create', 'record-pause-inspect', 'record-pause-execute', 'record-pause-verify', 'snapshot', 'snapshot-check'])) fail('maintenance must expose the exact reviewed pause, recovery and snapshot steps')
  if (!equal(Object.keys(maintenance.on), ['workflow_dispatch']) || !equal(maintenance.permissions, { contents: 'read' }) || !equal(maintenanceJob?.needs, ['offline', 'target']) || maintenanceJob?.environment !== '${{ needs.target.outputs.environment }}' || maintenanceJob?.if !== "github.ref == 'refs/heads/main' && vars.AWS_MAINTENANCE_ENABLED == 'true'") fail('maintenance must be manual, main-only, disabled by default and protected')
  if (!equal(maintenanceJob.concurrency, { group: 'fitfinity-${{ needs.target.outputs.environment }}', 'cancel-in-progress': false }) || !equal(maintenanceJob.permissions, { contents: 'read', actions: 'read', 'id-token': 'write' }) || maintenance.jobs.offline.uses !== './.github/workflows/infrastructure.yml') fail('maintenance concurrency, verification or permissions differ')
  const maintenanceAuth = maintenanceJob.steps.findIndex(step => step.uses?.startsWith('aws-actions/configure-aws-credentials@'))
  const maintenanceEvidence = maintenanceJob.steps.findIndex(step => step.run?.includes('maintenance_operator.py fetch'))
  if (maintenanceEvidence < 0 || maintenanceAuth <= maintenanceEvidence || maintenanceJob.steps[maintenanceEvidence].env?.REVIEW_SHA256 !== '${{ inputs.review_sha256 }}') fail('reviewed maintenance evidence must precede AWS credentials')
  const maintenanceCredentials = maintenanceJob.steps[maintenanceAuth].with
  if (maintenanceCredentials['role-to-assume'] !== '${{ vars.AWS_MAINTENANCE_ROLE_ARN }}' || maintenanceCredentials['allowed-account-ids'] !== '${{ needs.target.outputs.account }}' || maintenanceCredentials['aws-region'] !== '${{ needs.target.outputs.region }}' || maintenanceCredentials['unset-current-credentials'] !== true) fail('maintenance credential target differs')
  if (maintenance.jobs.target.outputs.role !== '${{ steps.target.outputs.maintenance_role }}') fail('maintenance must use its separate target role')
  const maintenanceRole = maintenanceJob.steps.find(step => step.run === 'test "$MAINTENANCE_ROLE" = "$EXPECTED_ROLE"')
  if (maintenanceRole?.env?.MAINTENANCE_ROLE !== '${{ vars.AWS_MAINTENANCE_ROLE_ARN }}' || maintenanceRole?.env?.EXPECTED_ROLE !== '${{ needs.target.outputs.role }}') fail('maintenance role comparison missing')
  const maintenanceReceipt = maintenanceJob.steps.find(step => step.uses?.startsWith('actions/upload-artifact@'))
  if (maintenanceReceipt?.if !== 'always()' || maintenanceReceipt?.with?.path !== '${{ runner.temp }}/maintenance-receipt.json') fail('maintenance must retain failed and uncertain receipts')
  for (const step of maintenanceJob.steps) {
    if (step['continue-on-error'] || (step.run ?? '').includes('${{ inputs.')) fail('maintenance must not interpolate input into shell or suppress errors')
  }
  const probeJob = schemaProbe.jobs?.probe
  if (!equal(Object.keys(schemaProbe.on), ['workflow_dispatch']) || !equal(schemaProbe.permissions, { contents: 'read' }) || !equal(probeJob?.needs, ['offline', 'target']) || probeJob?.environment !== '${{ needs.target.outputs.environment }}' || probeJob?.if !== "github.ref == 'refs/heads/main' && vars.AWS_SCHEMA_PROBE_ENABLED == 'true'") fail('schema probe must be manual, main-only, disabled by default and protected')
  if (!equal(probeJob.concurrency, { group: 'fitfinity-${{ needs.target.outputs.environment }}', 'cancel-in-progress': false }) || probeJob['timeout-minutes'] !== 10 || schemaProbe.jobs.offline.uses !== './.github/workflows/infrastructure.yml') fail('schema probe lifecycle concurrency or verification differs')
  const probeCredentials = probeJob.steps.find(step => step.uses?.startsWith('aws-actions/configure-aws-credentials@'))
  if (probeCredentials?.with?.['role-to-assume'] !== '${{ vars.AWS_SCHEMA_PROBE_ROLE_ARN }}' || probeCredentials.with['allowed-account-ids'] !== '${{ needs.target.outputs.account }}' || probeCredentials.with['aws-region'] !== '${{ needs.target.outputs.region }}') fail('schema probe must use its dedicated exact account role')
  const targetJob = schemaProbe.jobs.target
  if (targetJob?.if !== "github.ref == 'refs/heads/main'" || !equal(targetJob?.permissions, { contents: 'read' })) fail('target resolution must be main-only and credential-free')
  requireGate(targetJob, 'python3 backend/infrastructure/deployment_profile.py')
  const targetStep = targetJob.steps.find(step => step.id === 'target')
  if (targetStep?.env?.DEPLOYMENT_TARGET !== '${{ inputs.target }}' || targetStep.run.includes('${{')) fail('target input must use environment binding')
  for (const key of ['profile', 'profile_sha256', 'environment', 'account', 'region', 'role']) {
    if (targetJob.outputs?.[key] !== '${{ steps.target.outputs.' + key + ' }}') fail('target output binding differs')
  }
  const dedicated = probeJob.steps.find(step => step.name === 'Require dedicated probe role')
  if (dedicated?.env?.EXPECTED_ROLE !== '${{ needs.target.outputs.role }}' || dedicated.run !== 'test "$PROBE_ROLE" = "$EXPECTED_ROLE"') fail('dedicated target role check differs')
  for (const command of ['schema_probe_artifacts.py', 'schema_probe_operator.py']) {
    const step = probeJob.steps.find(step => step.run?.includes(command))
    if (step?.env?.DEPLOYMENT_PROFILE !== '${{ needs.target.outputs.profile }}') fail('probe must consume resolved profile')
  }
  requireGate(probeJob, 'python3 backend/infrastructure/schema_probe_artifacts.py')
  requireGate(probeJob, 'python3 backend/infrastructure/schema_probe_operator.py')
  if (probeJob.steps.findIndex(step => step.run?.includes('schema_probe_artifacts.py')) > probeJob.steps.indexOf(probeCredentials)) fail('probe evidence must be fetched before authentication')
  const probeUpload = probeJob.steps.find(step => step.uses?.startsWith('actions/upload-artifact@'))
  if (probeUpload?.if !== 'always()' || probeUpload.with['retention-days'] !== 7 || probeUpload.with.path !== '${{ runner.temp }}/schema-probe-receipt.json') fail('probe must retain only its operational receipt')
  const observe = observation.jobs?.observe
  if (!equal(Object.keys(observation.on), ['workflow_dispatch']) || !equal(observation.permissions, { contents: 'read' }) || !equal(observe?.needs, ['offline', 'target']) || observe.environment !== '${{ needs.target.outputs.environment }}' || observe.if !== "github.ref == 'refs/heads/main'") fail('release observation must stay manual, main-only and protected')
  const observationCredentials = observe.steps.find(step => step.uses?.startsWith('aws-actions/configure-aws-credentials@'))
  if (observationCredentials?.with?.['allowed-account-ids'] !== '${{ needs.target.outputs.account }}' || observationCredentials.with['aws-region'] !== '${{ needs.target.outputs.region }}' || observationCredentials.with['role-to-assume'] !== '${{ vars.AWS_HOSTING_ROLE_ARN }}') fail('release observation identity differs')
  if (observationCredentials.with['inline-session-policy'] !== '${{ needs.target.outputs.observation_policy }}') fail('release observation must use the scoped target read policy')
  if (!equal(observe.concurrency, { group: 'fitfinity-${{ needs.target.outputs.environment }}', 'cancel-in-progress': false })) fail('observation must serialize target operations')
  const observeTarget = observation.jobs.target
  if (observeTarget?.if !== "github.ref == 'refs/heads/main'" || !equal(observeTarget?.permissions, { contents: 'read' })) fail('observation target resolver requires main and no credentials')
  requireGate(observeTarget, 'python3 backend/infrastructure/deployment_profile.py')
  for (const key of ['profile', 'environment', 'account', 'region', 'hosting_role', 'observation_policy']) {
    if (observeTarget.outputs?.[key] !== '${{ steps.target.outputs.' + key + ' }}') fail('observation target output differs')
  }
  requireGate(observe, 'test "$HOSTING_ROLE" = "$EXPECTED_ROLE"')
  if (observe.steps.find(step => step.env?.HOSTING_ROLE)?.env?.EXPECTED_ROLE !== '${{ needs.target.outputs.hosting_role }}') fail('observation role differs')
  requireGate(observe, 'python3 backend/infrastructure/release_observation.py --profile "$DEPLOYMENT_PROFILE" --output')
  if (observe.steps.find(step => step.run?.includes('release_observation.py'))?.env?.DEPLOYMENT_PROFILE !== '${{ needs.target.outputs.profile }}') fail('observation profile differs')
  const caller = pages.jobs?.verify
  if (caller?.uses !== './.github/workflows/verify.yml' || caller.if != null || caller.secrets != null || caller['continue-on-error']) fail('PR and main must call the complete verification workflow unconditionally')
  if (!Object.hasOwn(verify.on ?? {}, 'workflow_call') || !equal(verify.permissions, { contents: 'read' })) fail('shared verification must be callable with read-only repository access')
  for (const [name, job] of Object.entries(verify.jobs ?? {})) {
    if (Object.values(job.env ?? {}).some(value => /\$\{\{[^}]*\brunner\./.test(String(value)))) fail('runner context is only available after job scheduling; use step env')
    if ((job.if != null && !(['api-browser', 'frontend', 'backend'].includes(name) && job.if === 'always()')) || job['continue-on-error'] || job.environment || job.secrets || Object.entries(job.permissions ?? {}).some(([key, value]) => key !== 'contents' || value !== 'read')) fail('verification jobs must be unconditional without deployment credentials')
    if ((job.steps ?? []).some(step => /configure-aws-credentials|deploy-pages/.test(step.uses ?? ''))) fail('deployment action in verification')
  }
  const shard = verify.jobs?.['api-browser-shard'], aggregate = verify.jobs?.['api-browser']
  if (!equal(shard?.strategy, { 'fail-fast': false, matrix: { shard: [1, 2] } }) || shard['runs-on'] !== 'ubuntu-24.04' || shard['timeout-minutes'] !== 20) fail('both isolated shards must retain the reviewed runner and budget')
  if (aggregate?.needs !== 'api-browser-shard' || aggregate.if !== 'always()') fail('aggregate must run after both shards, including failures')
  requireGate(shard, 'sudo python3 scripts/prepare-browser-apt.py /etc/apt/sources.list.d/ubuntu.sources')
  requireGate(shard, 'npx playwright install --with-deps chromium webkit')
  requireGate(shard, 'npm run test:api-browser -- --shard=${{ matrix.shard }}/2 --reporter=list,json')
  requireGate(aggregate, 'npx playwright test --config=playwright.api.config.js --list --reporter=json')
  requireGate(aggregate, 'node scripts/verify-api-shards.mjs')
  const aggregateStep = aggregate.steps.find(step => step.run?.includes('node scripts/verify-api-shards.mjs'))
  if (aggregateStep.env?.API_BROWSER_SHARD_RESULT !== '${{ needs.api-browser-shard.result }}') fail('aggregate must verify successful shard job outcomes')
  const jobs = verify.jobs, quality = jobs.quality, browser = jobs['browser-profile']
  for (const [name, needs] of Object.entries({ frontend: ['quality', 'unit', 'browser-build', 'browser-profile'], backend: ['backend-checks', 'infrastructure', 'backend-group'] })) {
    const job = jobs[name]
    if (!equal(job?.needs, needs) || job.if !== 'always()') fail('complete aggregate dependencies required')
    requireGate(job, `node scripts/verify-ci-groups.mjs ${name}`)
    if (job.steps.find(step => step.run?.includes('verify-ci-groups')).env?.CI_NEEDS !== '${{ toJSON(needs) }}') fail('aggregate needs must be authentic')
  }
  for (const name of ['quality', 'unit', 'browser-build', 'backend-checks', 'infrastructure', 'backend-group', 'api-browser-shard']) {
    if (!jobs[name] || jobs[name].needs != null) fail('independent verification must start concurrently')
  }
  if (browser?.['runs-on'] !== 'macos-15' || browser.needs !== 'browser-build' || !equal(browser.strategy, { 'fail-fast': false, matrix: { profile: ['desktop-chromium', 'phone', 'tablet'] } })) fail('complete macOS browser profile matrix required')
  if (!equal(jobs['backend-group'].strategy, { 'fail-fast': false, matrix: { group: ['identity-clients', 'scheduling-packages', 'records-platform'] } })) fail('complete backend domain partition required')
  if (jobs['backend-group'].env?.FITFINITY_TEST_GROUP !== '${{ matrix.group }}' || jobs['backend-group'].steps.find(step => step.name === 'Isolated backend group')?.env?.FITFINITY_BACKEND_RECEIPT !== '${{ runner.temp }}/backend-group.json') fail('backend group binding required')
  for (const command of ['npm ci', 'npm audit --include=dev --audit-level=high --json', 'npm run verify:lint', 'npm run verify:dependencies', 'npm run verify:quality-checker', 'npm run verify:health-checker', 'npm run verify:health']) requireGate(quality, command)
  for (const command of ['npm test -- --reporter=verbose', 'node scripts/verify-test-results.mjs unit']) requireGate(jobs.unit, command)
  for (const command of ['npm run build', 'npm run build:pages-test', 'npm run build:api-test', 'npm run verify:pwa -- dist /', 'npm run verify:pwa -- dist-pages /FitfinityReact/', 'npm run verify:pwa -- dist-api-test /']) requireGate(jobs['browser-build'], command)
  for (const command of ['npx playwright install --with-deps chromium webkit', 'npx playwright test --project=${{ matrix.profile }} --workers=1 --reporter=list,json']) requireGate(browser, command)
  requireGate(browser, 'test "$(cat browser-build-sha.txt)" = "$GITHUB_SHA"')
  for (const name of ['browser-profile', 'backend-group']) {
    const retained = jobs[name].steps.filter(step => step.uses?.startsWith('actions/upload-artifact@'))
    if (retained.length !== 1 || retained[0].if !== 'always()' || retained[0].with?.['if-no-files-found'] !== 'error') fail('group evidence must survive failures and reject missing reports')
  }
  const auditArtifacts = quality.steps.filter(step => step.uses?.startsWith('actions/upload-artifact@') && step.with?.path?.split('\n').includes('${{ runner.temp }}/fitfinity-npm-audit.json'))
  if (auditArtifacts.length !== 1 || auditArtifacts[0].if !== 'always()') fail('npm audit evidence must survive failed verification')
  for (const command of ['node scripts/verify-assessment-forms.mjs', 'node scripts/verify-backend.mjs backend-checks']) requireGate(jobs['backend-checks'], command)
  requireGate(jobs.infrastructure, 'node scripts/verify-infrastructure.mjs')
  requireGate(jobs['backend-group'], 'node scripts/verify-backend.mjs')
  const mainOnly = "github.event_name != 'pull_request' && github.ref == 'refs/heads/main'"
  if (pages.jobs?.build?.needs !== 'verify' || pages.jobs.build.if !== mainOnly || pages.jobs?.deploy?.needs !== 'build' || pages.jobs.deploy.if !== mainOnly) fail('Pages build and publish must depend on full verification and the main-branch guard')
  const imageJob = image?.jobs?.image
  const releaseGuard = "github.ref == 'refs/heads/main' && vars.AWS_IMAGE_RELEASE_ENABLED == 'true'"
  if (pages.jobs?.image || Object.values(pages.jobs ?? {}).some(job => job.uses === './.github/workflows/aws-image.yml')) fail('normal verification must not queue or wait for image publication')
  if (!equal(Object.keys(image?.on ?? {}), ['workflow_dispatch']) || !equal(image.on.workflow_dispatch?.inputs?.source_sha, { description: 'Exact main commit to verify and publish (40-character SHA)', required: true, type: 'string' }) || !equal(image.permissions, { contents: 'read' }) || !equal(imageJob.concurrency, { group: 'fitfinity-${{ needs.source.outputs.environment }}', 'cancel-in-progress': false })) fail('image workflow requires manual exact-source selection and serialized AWS operations')
  const source = image.jobs?.source, releaseVerify = image.jobs?.verify
  if (source?.if !== releaseGuard || source.environment || source['continue-on-error'] || source.permissions || source.steps?.length !== 3) fail('release source selection requires main, explicit activation and no deployment credentials')
  const selection = source.steps[0]
  if (selection.env?.EXPECTED_SHA !== '${{ inputs.source_sha }}') fail('release must bind the explicitly entered source SHA')
  requireGate(source, '[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]')
  requireGate(source, 'test "$EXPECTED_SHA" = "$GITHUB_SHA"')
  if (releaseVerify?.needs !== 'source' || releaseVerify.uses !== './.github/workflows/verify.yml' || releaseVerify.if != null || releaseVerify.secrets || releaseVerify['continue-on-error']) fail('manual release must run all verification after source selection')
  if (!equal(imageJob?.needs, ['verify', 'source']) || imageJob.if !== `github.event_name == 'workflow_dispatch' && ${releaseGuard}` || imageJob.environment !== '${{ needs.source.outputs.environment }}' || imageJob['continue-on-error'] || !equal(imageJob.permissions, { contents: 'read', 'id-token': 'write' })) fail('image publication requires complete verification, its protected environment and narrow credentials')
  const imageCredentials = imageJob.steps.filter(step => (step.uses ?? '').startsWith('aws-actions/configure-aws-credentials@'))
  if (imageCredentials.length !== 1 || imageCredentials[0].with?.['role-to-assume'] !== '${{ vars.AWS_IMAGE_ROLE_ARN }}' || imageCredentials[0].with?.['allowed-account-ids'] !== '${{ needs.source.outputs.account }}' || imageCredentials[0].with?.['aws-region'] !== '${{ needs.source.outputs.region }}') fail('image publication must use its separate exact-account role')
  requireGate(imageJob, 'test "$IMAGE_ROLE" = "$EXPECTED_ROLE"')
  requireGate(imageJob, 'python3 backend/infrastructure/deploy.py image-candidate --actions --profile "$DEPLOYMENT_PROFILE" --receipt')
  requireGate(source, 'python3 backend/infrastructure/deployment_profile.py')
  if (source.steps.find(step => step.id === 'target')?.env?.DEPLOYMENT_TARGET !== '${{ inputs.target }}') fail('image target input differs')
  for (const key of ['profile', 'environment', 'account', 'region', 'image_role']) {
    if (source.outputs?.[key] !== '${{ steps.target.outputs.' + key + ' }}') fail('image target output differs')
  }
  if (imageJob.steps.find(step => step.env?.IMAGE_ROLE)?.env?.EXPECTED_ROLE !== '${{ needs.source.outputs.image_role }}') fail('image target role check differs')
  if (imageJob.steps.find(step => step.run?.includes('deploy.py image-candidate'))?.env?.DEPLOYMENT_PROFILE !== '${{ needs.source.outputs.profile }}') fail('image profile binding differs')
  const acceptanceGuard = "github.repository == 'LimYouSheng/FitfinityReact' && github.ref == 'refs/heads/main'"
  const acceptJob = acceptance?.jobs?.accept
  if (!equal(Object.keys(acceptance?.on ?? {}), ['workflow_dispatch']) || acceptance.jobs?.verify?.uses !== './.github/workflows/verify.yml' || acceptance.jobs.verify.if !== acceptanceGuard || acceptJob?.needs !== 'verify' || acceptJob.if !== acceptanceGuard || acceptJob.environment !== 'aws-test' || acceptJob['continue-on-error']) fail('existing-image acceptance requires manual main execution after full verification')
  if (!equal(acceptance.permissions, { contents: 'read' }) || !equal(acceptance.concurrency, { group: 'fitfinity-aws-test', 'cancel-in-progress': false }) || !equal(acceptJob.permissions, { contents: 'read', actions: 'read', 'pull-requests': 'read', 'id-token': 'write' })) fail('image acceptance permissions or serialization differ')
  const credential = acceptJob.steps.filter(step => (step.uses ?? '').startsWith('aws-actions/configure-aws-credentials@'))
  if (credential.length !== 1 || credential[0].with?.['role-to-assume'] !== '${{ vars.AWS_IMAGE_ROLE_ARN }}' || credential[0].with?.['allowed-account-ids'] !== '418638389566' || credential[0].with?.['aws-region'] !== 'ap-southeast-1') fail('image acceptance requires the exact account and role')
  const sessionPolicy = JSON.parse(credential[0].with['inline-session-policy'] ?? '{}')
  const expectedReadPolicy = { Version: '2012-10-17', Statement: [{ Effect: 'Allow', Action: ['sts:GetCallerIdentity', 'ecr:GetRegistryScanningConfiguration'], Resource: '*' }, { Effect: 'Allow', Action: ['ecr:DescribeRepositories', 'ecr:ListTagsForResource', 'ecr:BatchGetImage', 'ecr:DescribeImageScanFindings'], Resource: 'arn:aws:ecr:ap-southeast-1:418638389566:repository/fitfinity-test-api' }] }
  if (!equal(sessionPolicy, expectedReadPolicy)) fail('existing-image credentials must be restricted to exact read operations')
  requireGate(acceptJob, 'test "$IMAGE_ROLE" = \'arn:aws:iam::418638389566:role/fitfinity-test-github-image\'')
  requireGate(acceptJob, 'python3 backend/infrastructure/deploy.py image-accept --actions --digest')
  if (!Object.hasOwn(infrastructure.on ?? {}, 'workflow_call') || !Object.hasOwn(infrastructure.on, 'workflow_dispatch') || Object.hasOwn(infrastructure.on, 'pull_request')) fail('standalone infrastructure checks must remain manual/callable without duplicating full PR gates')
  for (const name of ['eslint', '@eslint/js', 'eslint-plugin-react-hooks', 'globals', 'rolldown', 'css-tree', 'yaml', '@testing-library/jest-dom', '@testing-library/react', '@testing-library/user-event', '@vitejs/plugin-react', 'jsdom', 'semver', 'smol-toml']) {
    const version = packageJson.devDependencies?.[name]
    if (!/^\d+\.\d+\.\d+$/.test(version ?? '') || lock.packages?.['']?.devDependencies?.[name] !== version || lock.packages?.[`node_modules/${name}`]?.version !== version) fail(`declare and lock direct tooling dependency: ${name}`)
  }
  const updates = dependabot?.updates
  if (dependabot?.version !== 2 || updates?.length !== 3) fail('dependency automation must retain the three reviewed ecosystems')
  for (const [ecosystem, directory, limit] of [['npm', '/', 1], ['github-actions', '/', 1], ['docker', '/backend', 1]]) {
    const matches = updates.filter(update => update['package-ecosystem'] === ecosystem)
    const update = matches[0]
    if (matches.length !== 1 || update.directory !== directory || update['open-pull-requests-limit'] !== limit || !equal(update.schedule, { interval: 'weekly', day: 'monday', time: '09:00', timezone: 'Asia/Singapore' }) || update['target-branch'] || update['insecure-external-code-execution']) fail(`bounded default-branch dependency updates required: ${ecosystem}`)
    if (ecosystem === 'npm' && !equal(update.groups, { 'npm-security': { 'applies-to': 'security-updates', patterns: ['*'], 'exclude-patterns': ['typescript', 'eslint*', '@eslint/*', '@typescript-eslint/*', '@playwright/*', 'playwright*', 'wrangler', 'miniflare'], 'update-types': ['minor', 'patch'] }, 'npm-minor-patch': { 'applies-to': 'version-updates', patterns: ['*'], 'exclude-patterns': ['typescript', 'eslint*', '@eslint/*', '@typescript-eslint/*', '@playwright/*', 'playwright*', 'wrangler', 'miniflare'], 'update-types': ['minor', 'patch'] } })) fail('npm majors must remain separate from routine grouped updates')
    if (ecosystem === 'github-actions' && !equal(update.groups, { 'actions-minor-patch': { patterns: ['*'], 'update-types': ['minor', 'patch'] } })) fail('compatible Actions updates must be grouped')
    if (ecosystem === 'docker' && (!equal(update.groups, { 'docker-patches': { patterns: ['*'], 'update-types': ['patch'] } }) || !equal(update.ignore, [{ 'dependency-name': 'python', 'update-types': ['version-update:semver-major', 'version-update:semver-minor'] }]))) fail('Docker patches must be grouped within the supported Python minor')
  }
  if (packageJson.scripts?.['verify:lint'] !== 'node scripts/verify-lint.mjs' || packageJson.scripts?.['verify:quality-checker'] !== 'node --test --test-reporter=spec scripts/verify-quality.test.mjs') fail('canonical quality commands are missing')
}

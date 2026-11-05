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
    packageJson: JSON.parse(read('package.json')),
    lock: JSON.parse(read('package-lock.json')),
  }
}

export function verifyQualitySetup({ dependabot, pages, verify, infrastructure, image, acceptance, preparation, observation, packageJson, lock }) {
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
  requireGate(preparation.jobs['frontend-and-schema'], 'python3 backend/infrastructure/release_readiness.py')
  requireGate(preparation.jobs['runtime-build'], 'docker build --pull --platform linux/amd64 --target runtime')
  const observe = observation.jobs?.observe
  if (!equal(Object.keys(observation.on), ['workflow_dispatch']) || !equal(observation.permissions, { contents: 'read' }) || observe?.needs !== 'offline' || observe.environment !== 'aws-test' || observe.if !== "github.repository == 'LimYouSheng/FitfinityReact' && github.ref == 'refs/heads/main'") fail('release observation must stay manual, main-only and protected')
  const observationCredentials = observe.steps.find(step => step.uses?.startsWith('aws-actions/configure-aws-credentials@'))
  if (observationCredentials?.with?.['allowed-account-ids'] !== '418638389566' || observationCredentials.with['role-to-assume'] !== '${{ vars.AWS_HOSTING_ROLE_ARN }}') fail('release observation identity differs')
  const readPolicy = JSON.parse(observationCredentials.with['inline-session-policy'])
  const allowedReads = ['sts:GetCallerIdentity', 'cloudformation:DescribeStacks', 'cloudformation:GetTemplate', 'lambda:GetFunction', 'lambda:GetAlias', 'rds:DescribeDBInstances']
  if (readPolicy.Statement.some(statement => statement.Effect !== 'Allow' || statement.NotAction || statement.NotResource || [].concat(statement.Action).some(action => !allowedReads.includes(action)))) fail('release observation policy must be read-only without secret access')
  requireGate(observe, 'python3 backend/infrastructure/release_observation.py --output')
  const caller = pages.jobs?.verify
  if (caller?.uses !== './.github/workflows/verify.yml' || caller.if != null || caller.secrets != null || caller['continue-on-error']) fail('PR and main must call the complete verification workflow unconditionally')
  if (!Object.hasOwn(verify.on ?? {}, 'workflow_call') || !equal(verify.permissions, { contents: 'read' })) fail('shared verification must be callable with read-only repository access')
  for (const [name, job] of Object.entries(verify.jobs ?? {})) {
    if (Object.values(job.env ?? {}).some(value => /\$\{\{[^}]*\brunner\./.test(String(value)))) fail('runner context is only available after job scheduling; use step env')
    if ((job.if != null && !(['api-browser', 'frontend', 'backend'].includes(name) && job.if === 'always()')) || job['continue-on-error'] || job.environment || job.secrets || Object.entries(job.permissions ?? {}).some(([key, value]) => key !== 'contents' || value !== 'read')) fail('verification jobs must be unconditional without deployment credentials')
    if ((job.steps ?? []).some(step => /configure-aws-credentials|deploy-pages/.test(step.uses ?? ''))) fail('deployment action in verification')
  }
  const shard = verify.jobs?.['api-browser-shard'], aggregate = verify.jobs?.['api-browser']
  if (!equal(shard?.strategy, { 'fail-fast': false, matrix: { shard: [1, 2] } }) || shard['runs-on'] !== 'ubuntu-latest' || shard['timeout-minutes'] !== 20) fail('both isolated shards must retain the reviewed runner and budget')
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
  const releaseGuard = "github.repository == 'LimYouSheng/FitfinityReact' && github.ref == 'refs/heads/main' && vars.AWS_IMAGE_RELEASE_ENABLED == 'true'"
  if (pages.jobs?.image || Object.values(pages.jobs ?? {}).some(job => job.uses === './.github/workflows/aws-image.yml')) fail('normal verification must not queue or wait for image publication')
  if (!equal(Object.keys(image?.on ?? {}), ['workflow_dispatch']) || !equal(image.on.workflow_dispatch?.inputs?.source_sha, { description: 'Exact main commit to verify and publish (40-character SHA)', required: true, type: 'string' }) || !equal(image.permissions, { contents: 'read' }) || !equal(image.concurrency, { group: 'fitfinity-aws-test', 'cancel-in-progress': false })) fail('image workflow requires manual exact-source selection and serialized AWS operations')
  const source = image.jobs?.source, releaseVerify = image.jobs?.verify
  if (source?.if !== releaseGuard || source.environment || source['continue-on-error'] || source.permissions || source.steps?.length !== 1) fail('release source selection requires main, explicit activation and no deployment credentials')
  const selection = source.steps[0]
  if (selection.env?.EXPECTED_SHA !== '${{ inputs.source_sha }}') fail('release must bind the explicitly entered source SHA')
  requireGate(source, '[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]')
  requireGate(source, 'test "$EXPECTED_SHA" = "$GITHUB_SHA"')
  if (releaseVerify?.needs !== 'source' || releaseVerify.uses !== './.github/workflows/verify.yml' || releaseVerify.if != null || releaseVerify.secrets || releaseVerify['continue-on-error']) fail('manual release must run all verification after source selection')
  if (imageJob?.needs !== 'verify' || imageJob.if !== `github.event_name == 'workflow_dispatch' && ${releaseGuard}` || imageJob.environment !== 'aws-test' || imageJob['continue-on-error'] || !equal(imageJob.permissions, { contents: 'read', 'id-token': 'write' })) fail('image publication requires complete verification, its protected environment and narrow credentials')
  const imageCredentials = imageJob.steps.filter(step => (step.uses ?? '').startsWith('aws-actions/configure-aws-credentials@'))
  if (imageCredentials.length !== 1 || imageCredentials[0].with?.['role-to-assume'] !== '${{ vars.AWS_IMAGE_ROLE_ARN }}' || imageCredentials[0].with?.['allowed-account-ids'] !== '418638389566' || imageCredentials[0].with?.['aws-region'] !== 'ap-southeast-1') fail('image publication must use its separate exact-account role')
  requireGate(imageJob, 'test "$IMAGE_ROLE" = \'arn:aws:iam::418638389566:role/fitfinity-test-github-image\'')
  requireGate(imageJob, 'python3 backend/infrastructure/deploy.py image-candidate --actions --receipt')
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

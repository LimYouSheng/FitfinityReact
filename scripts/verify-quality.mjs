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
    pages: parse(read('.github/workflows/pages.yml')),
    verify: parse(read('.github/workflows/verify.yml')),
    infrastructure: parse(read('.github/workflows/infrastructure.yml')),
    image: parse(read('.github/workflows/aws-image.yml')),
    acceptance: parse(read('.github/workflows/aws-image-accept.yml')),
    packageJson: JSON.parse(read('package.json')),
    lock: JSON.parse(read('package-lock.json')),
  }
}

export function verifyQualitySetup({ pages, verify, infrastructure, image, acceptance, packageJson, lock }) {
  for (const event of ['pull_request', 'push']) {
    if (!equal(pages.on?.[event]?.branches, ['main']) || Object.keys(pages.on[event]).some(key => key !== 'branches')) fail(`${event} must run all gates for main without path filtering`)
  }
  if (Object.hasOwn(pages.on, 'pull_request_target')) fail('PR checks must use pull_request')
  const caller = pages.jobs?.verify
  if (caller?.uses !== './.github/workflows/verify.yml' || caller.if != null || caller.secrets != null || caller['continue-on-error']) fail('PR and main must call the complete verification workflow unconditionally')
  if (!Object.hasOwn(verify.on ?? {}, 'workflow_call') || !equal(verify.permissions, { contents: 'read' })) fail('shared verification must be callable with read-only repository access')
  for (const job of Object.values(verify.jobs ?? {})) {
    if (job.if != null || job['continue-on-error'] || job.environment || job.secrets || Object.entries(job.permissions ?? {}).some(([key, value]) => key !== 'contents' || value !== 'read')) fail('verification jobs must be unconditional without deployment credentials')
    if ((job.steps ?? []).some(step => /configure-aws-credentials|deploy-pages/.test(step.uses ?? ''))) fail('deployment action in verification')
  }
  const frontend = verify.jobs?.frontend, backend = verify.jobs?.backend
  if (frontend?.['runs-on'] !== 'macos-15') fail('browser gates require the reviewed macOS WebKit runner')
  for (const command of ['npm ci', 'npm run verify:lint', 'npm run verify:quality-checker', 'npm test -- --reporter=verbose', 'node scripts/verify-test-results.mjs unit', 'npx playwright install --with-deps chromium webkit', 'npm run test:e2e -- --reporter=list', 'node scripts/verify-test-results.mjs browser', 'npm run verify:health-checker', 'npm run verify:health']) requireGate(frontend, command)
  for (const command of ['node scripts/verify-assessment-forms.mjs', 'node scripts/verify-backend.mjs']) requireGate(backend, command)
  const mainOnly = "github.event_name != 'pull_request' && github.ref == 'refs/heads/main'"
  if (pages.jobs?.build?.needs !== 'verify' || pages.jobs.build.if !== mainOnly || pages.jobs?.deploy?.needs !== 'build' || pages.jobs.deploy.if !== mainOnly) fail('Pages build and publish must depend on full verification and the main-branch guard')
  const imageCaller = pages.jobs?.image, imageJob = image?.jobs?.image
  if (imageCaller?.needs !== 'verify' || imageCaller.uses !== './.github/workflows/aws-image.yml' || imageCaller.if !== `${mainOnly} && vars.AWS_IMAGE_RELEASE_ENABLED == 'true'` || imageCaller['continue-on-error']) fail('image publication requires complete verification, main and explicit activation')
  if (!equal(image?.on, { workflow_call: null }) || !equal(image.permissions, { contents: 'read' }) || !equal(image.concurrency, { group: 'fitfinity-aws-test', 'cancel-in-progress': false })) fail('image workflow must be callable only and serialize AWS operations')
  if (imageJob?.if !== mainOnly || imageJob.environment !== 'aws-test' || imageJob['continue-on-error'] || !equal(imageJob.permissions, { contents: 'read', 'id-token': 'write' })) fail('image publication requires its protected environment and narrow credentials')
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
  for (const name of ['eslint', '@eslint/js', 'eslint-plugin-react-hooks', 'globals', 'rolldown', 'css-tree', 'yaml']) {
    const version = packageJson.devDependencies?.[name]
    if (!/^\d+\.\d+\.\d+$/.test(version ?? '') || lock.packages?.['']?.devDependencies?.[name] !== version || lock.packages?.[`node_modules/${name}`]?.version !== version) fail(`declare and lock direct tooling dependency: ${name}`)
  }
  if (packageJson.scripts?.['verify:lint'] !== 'node scripts/verify-lint.mjs' || packageJson.scripts?.['verify:quality-checker'] !== 'node --test --test-reporter=spec scripts/verify-quality.test.mjs') fail('canonical quality commands are missing')
}

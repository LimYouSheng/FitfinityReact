# How Fitfinity fits together

[System diagrams](diagram.md) · [Service contracts](../SERVICE_CONTRACTS.md) · [Current progress](../../PROGRESS.md)

This explanation describes the source architecture and its deployment boundary. The operation matrix identifies what is integrated; the progress ledger identifies what has passed CI and merged. These diagrams do not certify that current source is deployed to Lambda.

## Browser and service boundary

React/Vite provides the Owner, Admin and Trainer portal. `App.jsx` composes feature screens; `PortalDataProvider` loads authorized snapshots and rejects stale account/generation replies. One navigation owner retains account-scoped history and view state. Feature screens receive data and asynchronous service callbacks rather than owning persistence.

`defaultPortalServices` explicitly selects the demo or API adapter behind `createPortalServices`. Demo mode uses prototype records and browser storage. API mode calls FastAPI through `apiPortalAdapter` and the HTTP client; unsupported operations fail instead of silently using mocks. The 55 named contracts describe domain behavior, not an endpoint count. Capability flags let the interface expose supported workflows, while the server enforces permissions.

GitHub Pages serves the demo. The AWS frontend hosting path uses static assets behind CloudFront. A production frontend build and the Lambda image are separate release artifacts: merging frontend/API code does not update either deployed artifact automatically under coding authority.

## Identity and authorization

Cognito owns staff identity and authentication challenges. The backend verifies signed tokens and checks active staff identity, session state and operation-specific permissions. Cookie/CSRF handling and current actor checks are part of the API boundary. A browser role, hidden button or record ID cannot authorize a write.

Authorization also depends on current client/Trainer assignment, approval policy and record state. Owner/Admin operations, Owner-only financial decisions and Trainer self/assigned scopes remain distinct. The initial eleven assessment forms are Owner/Admin-only; assigned general health notes have a separate policy. The [contracts](../SERVICE_CONTRACTS.md#authority-and-privacy) own these rules.

## Application and durable data

FastAPI/Uvicorn runs ordinary HTTP. API routes and domain helpers validate requests, authorize the actor, acquire the necessary locks and perform the domain transaction. SQLAlchemy models and forward Alembic migrations define PostgreSQL persistence. PostgreSQL owns clients, Trainers, purchases, bookings, assessments, messages, requests, audit/credit evidence and command receipts. Schema presence does not imply a domain workflow is integrated.

Purchased terms and completed evidence are retained snapshots. Stable session IDs survive chronological renumbering and Open/scheduled transitions. A reviewed write rechecks versions, authority and conflicts and atomically saves its records, history/notices and receipt where required. Request decisions and cancellations serialize before taking actor/Trainer row locks so competing decisions have one committed winner. Lost responses reconcile the original actor/key; a retry does not invent a new intention. See the [write sequence](diagram.md#reviewed-write-and-recovery).

The exercise-plan candidate keeps typed ordered detail rows and stable item IDs. Removing an exercise retires its row instead of deleting result/media identities; original values remain in immutable command receipts. An existing legacy note is shown as an editable detail until the first reviewed save. Plan editing has its own capability and does not enable video, outcome or acknowledgement writes. Acceptance remains in the operation matrix.

S3 is the selected durable object/media boundary; it is not replaced by Lambda disk or browser storage. Protected upload/download, session media and reports remain subject to their matrix status and acceptance. Do not infer implemented media workflows from infrastructure or storage models.

## Deployment boundary

The selected AWS topology is CloudFront/static assets, regional API Gateway, Lambda with the Lambda Web Adapter, Cognito and private PostgreSQL/RDS, with S3 for objects. The application stays container-compatible so business logic is independent of Lambda invocation details. Database connections, private network egress, retained infrastructure identities and recovery constraints belong to the [AWS runbook](../AWS_DEPLOYMENT_RUNBOOK.md), not to a new architecture diagram approval.

`backend/Dockerfile` has a shared `application` stage. `test` adds test dependencies without fetching the Lambda adapter; `runtime` adds the pinned adapter and retains the production launch behavior. This isolates the ECR download dependency from backend tests. A runtime build, image publication, migration, deployment and production acceptance are separate actions and evidence levels.

## Real API testing and isolation

`tests-api/` drives the actual frontend through FastAPI, migrations, PostgreSQL, JWT verification, cookies, CSRF and authorization. `backend/tests/browser_server.py` supplies synthetic fixtures and a local signed-token identity provider. Cognito delivery/provisioning is substituted; the application API and database are real.

The browser verifier owns a temporary Compose project and test PostgreSQL, with worker-isolated databases. The test harness validates allowed test database URLs and excludes production targets. Compose cleanup removes its owned containers/volumes. Tests do not call production RDS or require a Lambda redeployment. Existing Node-simulator browser specs remain useful frontend evidence but do not establish database persistence.

Backend PostgreSQL tests exercise transaction rollback, permissions, versions and database invariants. Browser evidence adds UI writes, reload/fresh-login reads, scope checks and unknown-response recovery. Real Cognito, service restart, physical-device and live deployment acceptance remain separately recorded. Commands live in [CODEX_CLOUD](../CODEX_CLOUD.md).

## Engineering hardening and release evidence

Mutation testing, measured latency/throughput budgets, dependency/supply-chain maintenance, security/resilience and production drills are prioritized in [Progress](../../PROGRESS.md#engineering-hardening-backlog-planned-not-provisioned). OpenTelemetry/Grafana is planned, not a connected monitoring stack. Redaction, sampling, retention, cardinality, failure isolation and cost controls must precede activation.

All final-head frontend/backend/api-browser CI and GitHub requirements precede source merge. Deployment requires its own applicable authorization and reviewed artifact/migration evidence. A green synthetic suite proves only its stated scope. Current release fingerprints and expired historical approvals remain in the runbook and ledger.

## Code owners

| Responsibility | Source |
| --- | --- |
| Composition, snapshots and navigation | `src/App.jsx`, `src/components/PortalDataProvider.jsx`, `src/hooks/useAppNavigation.js` |
| Domain contracts and API transport | `src/services/portalContracts.js`, `apiPortalAdapter.js`, `apiClient.js` |
| UI and prototype rules | `src/features/`, `src/components/`, `src/app/` |
| HTTP, authority and domain transactions | `backend/app/` |
| Durable schema and migrations | `backend/app/models/`, `backend/migrations/` |
| Real database and browser evidence | `backend/tests/`, `tests-api/`, `backend/compose.browser.yaml` |
| Container and release evidence | `backend/Dockerfile`, `backend/infrastructure/`, `.github/workflows/` |

Adapted from SoccerBot [architecture explanation](https://github.com/LimYouSheng/SoccerBotStudioSG/blob/96814c08ecef/docs/Architecture/README.md) and [diagrams](https://github.com/LimYouSheng/SoccerBotStudioSG/blob/96814c08ecef/docs/Architecture/diagram.md). Fitfinity retains FastAPI/PostgreSQL/Cognito/AWS and its own execution authority; it does not inherit SoccerBot's Cloudflare/provider architecture or browser restrictions.

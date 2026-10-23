# How the system fits together

[System diagram](diagram.md) · [Current rules and dated history](../SERVICE_CONTRACTS.md)

**Staff interface.** React/Vite renders the Owner, Admin and Trainer portal. Feature screens use injected asynchronous services; `PortalDataProvider` owns authorized snapshots and `useAppNavigation` owns account-scoped history. Explicit demo mode uses prototype data and browser storage. API mode uses `apiPortalAdapter` and FastAPI without falling back to mocks. GitHub Pages hosts the separate demo export.

**Identity and application.** Cognito owns staff identity and authentication challenges. FastAPI verifies signed tokens, cookies/CSRF, active staff identity and current record permissions. Domain services recheck reviewed versions, assignment and conflicts inside the transaction. Browser capabilities describe available features; they do not grant authority.

**Durable storage and recovery.** PostgreSQL owns relational business records, purchased snapshots, audit/credit evidence and command receipts; SQLAlchemy and Alembic define models and forward schema changes. A command commits its effects and receipt together. A lost response is reconciled using the original actor and key. S3 is the selected durable media boundary; media and report workflows remain subject to the operation matrix. Application memory and local disk are not durable business stores.

**Hosting and portability.** The selected AWS topology serves static assets through CloudFront and routes API Gateway requests to FastAPI on Lambda through the Lambda Web Adapter. Cognito, private PostgreSQL/RDS and S3 have distinct responsibilities. The application remains ordinary container-compatible HTTP so hosting changes do not require rewriting business logic. Selected topology does not establish that current source is deployed; Progress owns observed deployment status.

**Testing.** Playwright's `tests-api/` runs the real frontend, FastAPI routes, migrations, JWT checks, cookies, CSRF and authorization against temporary Docker PostgreSQL with worker-isolated databases. Only Cognito is substituted by a local signed-token provider. The verifier rejects non-test database targets and removes its owned resources. Node-simulator browser tests remain separate frontend evidence. No Lambda deployment or production database is needed for these tests.

**Delivery and hardening.** The Docker `application` stage is shared; `test` adds test dependencies without downloading the Lambda adapter, while `runtime` adds the pinned adapter. Final-head frontend/backend/API-browser CI precedes source acceptance. Image publication, migrations, deployment and live/provider/device acceptance require their own evidence and applicable authorization. Mutation testing, measured performance budgets and OpenTelemetry/Grafana remain planned work in Progress, not existing capabilities. [Service Contracts](../SERVICE_CONTRACTS.md#deployment-migration-and-acceptance) owns release safeguards.

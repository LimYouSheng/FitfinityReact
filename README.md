# Fitfinity

Persistent FastAPI/PostgreSQL/Cognito implementation of the approved staff portal prototype. The goal is all **55 named domain operations**, plus authentication, route parity and release acceptance.

Read [AGENTS](AGENTS.md), [North Star](NORTH_STAR.md), [Progress](PROGRESS.md), then [Architecture](docs/Architecture/README.md) and the relevant [operation matrix and service contracts](docs/SERVICE_CONTRACTS.md).

| Document | Sole responsibility |
| --- | --- |
| AGENTS.md | Engineering workflow, verification and authority |
| NORTH_STAR.md | Product outcome and definition of done |
| PROGRESS.md | Current checkpoint, prioritized work and acceptance receipts |
| docs/SERVICE_CONTRACTS.md | Canonical operation matrix and service semantics |
| docs/Architecture/README.md | Component responsibilities and interactions |
| docs/Architecture/diagram.md | System, write/recovery, test and release diagrams |
| docs/CODEX_CLOUD.md | Development setup and verification commands |
| docs/AWS_DEPLOYMENT_RUNBOOK.md | Release, recovery and historical AWS evidence |
| docs/FITFINITY_JOURNEY.md | Historical decisions and milestone evidence |

GitHub Pages is the demo. Real API tests use isolated PostgreSQL and a local Cognito substitute. Neither establishes current Lambda deployment or real-provider acceptance. Current counts and evidence belong in Progress, not duplicated here.

Detailed previous decisions are retained under [docs/history](docs/history/README.md); current contracts and the ledger take precedence over dated status.

# Current system diagram

Selected Fitfinity architecture; current deployed source is recorded separately in [Progress](../../PROGRESS.md). Dashed media connections are planned or incomplete workflows. [One-page explanation](README.md) · [System rules](../SERVICE_CONTRACTS.md#part-1--current-system-rules).

```mermaid
flowchart TB
  Staff["Staff browser: React portal"]
  Pages["GitHub Pages: separate demo"]
  Demo["Demo adapter and browser storage"]
  subgraph AWS["Selected AWS topology"]
    Assets["CloudFront: static frontend"]
    Gateway["API Gateway"]
    App["Lambda Web Adapter and FastAPI"]
    Identity["Cognito: staff identity"]
    DB[("Private PostgreSQL / RDS")]
    Media[("S3: durable media")]
  end
  Assets --> Staff
  Pages --> Staff
  Staff -->|"Explicit demo mode"| Demo
  Staff -->|"API requests and authentication"| Gateway
  Gateway --> App
  App -->|"Identity verification"| Identity
  App -->|"Authorized transactions and receipts"| DB
  App -.->|"Protected media workflows"| Media
```

The browser selects one service mode; API errors never switch to demo. Source merge does not update Lambda. Arrows describe responsibilities, not deployment approval or completion of every operation.

## Isolated real-API testing

```mermaid
flowchart LR
  Tests["Playwright: real frontend"]
  subgraph Docker["Temporary test environment"]
    API["Real FastAPI application"]
    Tokens["Local signed-token provider"]
    PG[("Isolated PostgreSQL worker databases")]
    Seed["Alembic migrations and synthetic records"]
  end
  Tests -->|"UI writes, reloads and recovery"| API
  Tokens -->|"Substitutes Cognito only"| API
  API -->|"Real SQL and transactions"| PG
  Seed --> PG
```

The verifier owns test resources and cleanup. This environment has no production PostgreSQL target and makes no AWS/provider calls. Simulator browser tests are a separate suite; live Cognito, restart and physical-device acceptance require separate evidence.

# Deployment

This folder owns AWS installation, deployment configuration, workflow procedures, recovery and infrastructure evidence. The [operations Runbook](../runbook.md) owns routine checks, monitoring, incidents and dependency maintenance. [Journey](../journey.md) preserves the complete dated history.

| Area | Purpose |
| --- | --- |
| [CloudShell master setup](master-script/index.md) | First-account setup, adoption, saved review-preparation script and reconciliation of successful operator scripts. |
| [GitHub workflows](workflows/index.md) | CI/source selection, image and schema stages, manual/coordinated release, receipts, recovery and rollback. |
| [Infrastructure inventory](infrastructure.md) | Resource purposes, observed setup evidence, remaining live checks, DNS and retention policy. |

Source generation is not installation. A historic successful receipt is not a fresh inspection or permission to execute against a different account. Keep account-specific inputs and secrets private. User approval/merge and AWS execution boundaries remain unchanged.

After each setup or deployment change, update the affected resource row with its owner, purpose, source revision and observed outcome. Record successful CloudShell procedures and remaining integration gaps in the master-script reconciliation; update workflow explanations when sequencing, permissions or recovery contracts change. Keep dated execution evidence in Journey and the next action in Progress. Failed or uncertain operations remain unresolved until a readback or receipt establishes their outcome. This is a required documentation step, not a claim that an automatic AWS inventory sync is installed.

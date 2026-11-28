# Master setup reconciliation — 28 November 2026 (SGT)

The saved 27 November catalog remains intact at `/workspace/deployment-review/cloudshell-setup-catalog-20261127`. Its original source checkpoint is `85739549a806ee6a5b84e6258f921a60debf18bd`; it contains 15 stages, a manifest and account-bound successful-script evidence. Its archive and every Git stash are preserved. Raw account-specific transcripts remain local rather than becoming reusable client defaults.

The reviewed [prepare-review.sh](prepare-review.sh) is now retained beside the [setup guide](index.md). It invokes the current repository generators for foundation, hosting, probe/upgrade IAM and hosting access, producing local review artifacts. It makes no AWS calls. It is a preparation entry point, **not a finished unattended installer**.

| Area | Evidence reconciled | Remaining master-script work |
| --- | --- | --- |
| Hosting IAM | VPC reads, Lambda alias permissions and WAF read/tag corrections succeeded in the 26 November operator receipts. | Generate from current source and compare installed role plus boundary; do not replay obsolete one-action patches. |
| Private media S3 | User reported bucket installation and verified seven-day incomplete-multipart cleanup; completed objects do not expire under that rule. | Retain target-bound CORS, encryption/access checks and distinguish application media cleanup from bucket lifecycle. |
| Deployment journal S3 | User reported CREATE_COMPLETE and verification of trust, policy/boundary, encryption, versioning and bucket policy. Four child role grants were subsequently verified. | Add current journal setup/role augmentation to the master entry point; preserve conditional writes and read actual current claim/receipt state. |
| Recovery and retirement | Later coordinator work includes authenticated probe inputs, pre-backup retirement and protected backup/schema continuity. | Use current ownership/receipt contracts, not the catalog’s older stash; never delete uncertain workers or reset journal history. |
| Manual release | PR162/164 manual source6fc9410 completed schema0053 and successful resume46109484195. | Final receipt/temporary-worker cleanup still need reconciliation; source completion alone is not resource-cleanup evidence. |
| SES | Sender sheng@app404.ai selected; service wiring follows PR163. | Identity verification, sending authorization, configuration and durable event/email outcomes are not yet installed or accepted. |

Next: extend the entry point with the missing current generators and recovery-aware readback, then rehearse a synthetic client profile offline and a separately authorized fresh account. Preserve success/failure/uncertain state at every stage. No AWS operation was executed by this documentation consolidation.

The [source comparison](source-reconciliation.json) compares20 repository files with the inspected PR163 checkout and49 preserved workspace-local scripts/receipts with the archive. Changed owners need semantic reconciliation; an identical hash is not proof of current AWS state.

## Transactional email follow-up — 28 November 2026

The local SES candidate adds validated optional hosting bindings and sender-only Cognito preparation (`email_runtime.py`), plus a disabled worker template (`email_scheduler.py`). The setup sequence is owned by [email configuration](../email.md). These helpers are not yet a fully integrated CloudShell installer and have not run against AWS. Preserve the existing stashed catalog and successful account-specific receipts; do not replay historical setup. Remaining master integration: inspect existing sender/secret/pool/role owners, prepare only exact changed templates, preserve original bindings, then record authorized install/canary results.

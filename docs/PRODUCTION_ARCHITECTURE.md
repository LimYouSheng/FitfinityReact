# AWS production architecture contract — before M5

Preserve the architecture decision in the 7 September 2026 handoff. Chau/owner and
roughly 10+ trainers use the operational portal. Clients do not log into it; the public
website and later Glofox-gated member area are separate scope.

## Initial production

- Fitfinity/Chau owns the AWS account and billing. Root MFA; delegated IAM access.
- Primary business data/services in Singapore (`ap-southeast-1`).
- CloudFront + AWS WAF at the edge; HTTPS/DNS through appropriate AWS services.
- S3 static website and staff React/PWA assets behind CloudFront.
- Cognito for owner/trainer authentication. Backend enforces role and record relationships.
- API Gateway HTTP API → Lambda for initial backend compute.
- Private RDS PostgreSQL Single-AZ, encrypted, with automated backups, point-in-time
  recovery, deletion protection and a final-snapshot policy.
- S3 durable files/media; PostgreSQL stores metadata/references.
- CloudWatch logs/alarms, least-privilege IAM, managed secrets/configuration and budget alerts.

Planning target: roughly S$60–100/month, aiming below S$100 where practical. The roughly
S$200 previously communicated is headroom. These are inherited planning figures, not
new quotations; recheck actual AWS sizing/pricing and any Glofox charges before deployment.
Do not weaken database isolation, authentication, backups or monitoring to meet the target.

Do not add ALB, always-on EC2, NAT Gateway or Multi-AZ RDS solely for hypothetical scale.
Resolve private-network access, database connection management, external API egress and
its cost before implementation/deployment; the planning figure does not prove every
network path is free or already configured.

## Portable backend

One canonical stateless, container-compatible application with API/controller,
service/domain, authorization and repository boundaries. AWS adapters stay at the deployment
boundary. Business rules must not spread across Lambda handlers.

Durable data: PostgreSQL. Durable media: S3. Identities: Cognito. Secrets: managed storage.
No durable workflow state on local compute disks, Lambda `/tmp`, process memory or one instance.
Use stable API contracts/hostname and infrastructure-neutral migrations. Preserve transactional
credits, atomic approvals, saved remuneration evidence, stale-write checks and retry safety.

## Upgrade path

- API Gateway/Lambda → ALB + Auto Scaling/EC2, at least two application instances across AZs.
- RDS Single-AZ → Multi-AZ when availability requirements justify it.
- Expand private networking/NAT where needed by the selected compute and egress design.
- Retain CloudFront/WAF, S3, Cognito, PostgreSQL and frontend API contracts where appropriate.

This must remain an infrastructure/deployment migration with minimal application redevelopment.
Record any deliberate departure in the next handoff before building a conflicting backend.

## Future member exercise access

Staff and member privileges stay separate. Authentication identifies the person;
current membership eligibility authorizes access to approved instructional content.
Keep the canonical exercise catalogue, distinguish client session recordings from member
instructional videos, and grant private playback only after backend authorization.
The concrete Glofox integration is deferred and has not been verified for Chau's account.

# Phase 0 decisions

- Initial scope: one Microsoft tenant and an explicit initial recipient.
- Capture: post-meeting official transcript or separately authorized file upload; no live media capture.
- Scheduler: Power Automate owns the weekday 06:55 Australia/Sydney recurrence. Backend owns eligibility, word cap, idempotency and run record.
- Delivery: choose exactly one Power Automate or supported Graph sender after a tenant proof.
- Persistence: Neon PostgreSQL for business and durable job state; managed secret store for production credentials.
- Privacy: deterministic private-event exclusion before persistence/AI; conservative retention/deletion.
- Local demo: mock data only, localhost-bound ports, no real credentials and no claims of tenant integration.

Use `02-permissions-matrix.md`, `03-risk-register.md`, `01-phase0-tenant-checklist.md` and `06-phase1-go-no-go.md` for the full Phase 0 packet.


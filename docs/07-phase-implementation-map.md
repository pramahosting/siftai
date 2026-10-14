# Phase implementation map

| Phase | Included implementation | Remaining external validation |
|---|---|---|
| 0 — Decisions | Proposed ADRs, permission matrix, risk register, tenant checklist, go/no-go. | Product and M365 owners approve scope, access and retention. |
| 1 — Foundation | React/Vite, FastAPI, SQLAlchemy/Alembic, PostgreSQL, Docker, Entra token validation path, local-only demo token, admin authorization. | App registration, production secrets, Neon branch/TLS, host/CORS/TLS and review. |
| 2 — Calendar/briefing | Graph calendarView pagination, eligibility filter, private/cancelled/all-day exclusions, Sydney local day, three-day optional context adapter, preview and under-250-word final check. | Admin consent, context permission review, recurrence/DST proof and user-specific calendar behavior. |
| 3 — Jobs/delivery | Durable DB job table/worker, retry delay, lease recovery, scheduled API endpoint with unique user/date/run key, Power Automate delivery callback and failure email. | Host the API over HTTPS; configure flow owner, named timezone, Teams connector/target chat and callback secret; verify timeouts/replay. |
| 4 — Transcript/audio | Graph official transcript worker, VTT parsing/timestamps, authorized audio upload, Azure OpenAI Whisper transcription and job state. | Graph transcript policy and permissions; Azure OpenAI resource/deployment/data review; file size/retention review. Live capture is excluded. |
| 5 — Minutes/actions | Azure OpenAI structured (JSON-schema) extraction, overlapping hierarchical transcript chunks, evidence-bearing action candidates, editable versioned minutes, human review UI. | Evaluate extraction quality with approved representative transcripts; establish organizational approval workflow. |
| 6 — Admin/ops/release | Admin preferences/secret status, integration probes, audit records, job/run status, retention sweep, Docker docs, operator and test manual. | Production vault, log/backup erasure behavior, ops runbook, alerting, restore/rollback and acceptance sign-off. |

## Explicit capability boundaries

- Scheduled delivery is not activated by application startup. Power Automate must call the backend and post through one tenant-approved Teams connection.
- A `sent` delivery record is only written when the flow callback arrives. Lost callback after delivery is an `unknown` reconciliation case.
- Graph mail and chat-body context is disabled unless separately approved and enabled; the current broad application chat export path must undergo tenant/privacy review first.
- Graph token code uses client credentials for server-to-server access. It does not replace delegated Entra frontend sign-in configuration; confirm scopes and API audience in a real tenant.
- The demo transcript/minutes are fixtures. The demo does not call Azure OpenAI or Microsoft Graph.
- Local testing cannot establish tenant consent, production security, Azure OpenAI data-processing terms, Teams delivery or Power Automate DST behavior.


# Initial risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Tenant consent/policy blocks calendar or transcript API | Integration unavailable | Validate exact API, permission, policy and meeting type in a test tenant; keep unavailable capability disabled. |
| Teams chat route/identity unconfirmed | No scheduled delivery | Prove one sender route and test recipient; never dual-send. |
| DST/flow retries cause missing or duplicate briefing | Operational error | Named Sydney zone; unique backend key by user/local date/run type; test replay. |
| Partial calendar read interpreted as no meetings | Misleading briefing | Fail closed, paginate fully; clear-day only after verified empty. |
| Private or sensitive data reaches AI | Privacy harm | Deterministic exclusion before persistence/retrieval; test and audit. |
| Credentials in DB/UI/logs | Credential compromise | Server-side vault, replace-only settings, redaction tests and rotation. |
| Worker restart duplicates output | Repeated messages/jobs | Durable DB jobs, leases, uniqueness, retry and reconciliation. |
| AI invents decisions/actions | Incorrect minutes | Typed schemas, evidence pointers, draft status and human review. |
| Retention/deletion incomplete | Content retained unexpectedly | Per-class policy and deletion checks across DB/storage/jobs/logs; vendor review. |
| Azure OpenAI quota or API version changes | Processing failure | Configurable deployment names and API version, bounded retry with back-off and operator status. |


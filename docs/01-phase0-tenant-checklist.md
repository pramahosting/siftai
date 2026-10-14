# Non-production tenant validation checklist

Use test accounts, an approved test recipient and a non-production tenant. Do not add credential/token values or meeting content to this checklist.

| # | Check | Evidence to record | Status |
|---|---|---|---|
| 1 | Product owner confirms single-tenant MVP scope and first recipient. | Ticket/approval reference. | Not validated |
| 2 | Entra app registration and API audience reviewed. | App registration reference; no secret. | Not validated |
| 3 | Admin role/group tested; ordinary user is denied admin endpoints. | Sanitized authorization result. | Not validated |
| 4 | Calendar read mode and least-privilege permissions approved. | Permission, auth mode, approver, date. | Not validated |
| 5 | Calendar paging and denial tested; private/cancelled test events excluded. | Outcome only; no titles or attendee details. | Not validated |
| 6 | Tenant transcript API setting and permission path checked. | Policy/consent prerequisites. | Not validated |
| 7 | Controlled meeting transcript retrieved for intended organizer/attendee case. | Meeting type, status, speaker metadata availability. | Not validated |
| 8 | Missing/denied transcript and retry path checked. | Safe response category and job result. | Not validated |
| 9 | One direct Teams delivery route selected and tested. | Sender identity, destination, test receipt, license. | Not validated |
| 10 | Power Automate recurrence uses named Sydney timezone. | Owner, connection reference, timezone and run history. | Not validated |
| 11 | 06:55 schedule verified through DST change or controlled simulation. | UTC + Sydney timestamps. | Not validated |
| 12 | Production secret store and rotation process selected. | Vault reference/runbook, no values. | Not validated |
| 13 | Privacy, consent, retention, deletion and vendor processing reviewed. | Approval reference and permitted data classes. | Not validated |
| 14 | Failure notification tested without confidential content. | Sanitized outcome. | Not validated |


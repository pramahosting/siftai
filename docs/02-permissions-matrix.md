# Permissions and integration capability matrix

Exact permissions depend on Graph API version, auth mode and tenant policy. Validate each with the M365 administrator before consent. Calendar permission does not imply access to mail, chat, transcript or chat sending.

| Capability | Initial scope | Tenant decision/evidence |
|---|---|---|
| Entra sign-in | Delegated sign-in to app API. | App registration, audience, roles/group and admin bootstrap. |
| Calendar view | Needed for meeting list and briefing; start least privilege. | Mailbox principal, delegated/app-only mode, consent, paging, private events. Graph calendarView documents Calendars.ReadBasic as least privileged; verify required event properties. |
| Email context | Optional, disabled until approved. | Body-access scope, purpose and retention; avoid broad read without approval. |
| Teams context | Optional, disabled until approved. | Chat-specific permissions/RSC and policy. App-only chat access may be broad. Keep bodies out of persistent storage. |
| Online meeting transcript | Preferred post-meeting source. | Transcript permission, tenant API control, application access policy where required, meeting type/artifact availability. |
| Teams delivery | One direct-chat mechanism. | Power Automate connection identity/licensing or Graph route proven with exact permission/version. No dual-send. |
| Power Automate | Sole weekday scheduler. | Flow environment/owner, named Sydney timezone, secure backend token and DST run evidence. |
| Microsoft Copilot AI (Azure OpenAI in Microsoft Foundry) | Chat model deployment for briefings and minutes (structured output) and an optional Whisper deployment for audio transcription. | API key or Entra app role *Cognitive Services OpenAI User* on the resource; deployment names, quota and data-processing review. |
| Microsoft 365 Copilot Chat API (not used) | Beta Graph API, delegated user token only, no app-only access, broad read permissions. | Not suitable for the unattended worker; revisit when it is generally available with application permissions. |

Official references to re-check:

- Calendar view: https://learn.microsoft.com/en-us/graph/api/calendar-list-calendarview?view=graph-rest-1.0
- Transcript retrieval: https://learn.microsoft.com/en-us/graph/api/calltranscript-get?view=graph-rest-1.0
- Application access policy: https://learn.microsoft.com/en-us/graph/cloud-communication-online-meeting-application-access-policy
- Teams real-time media: https://learn.microsoft.com/en-us/microsoftteams/platform/bots/calls-and-meetings/real-time-media-concepts
- Azure OpenAI models and deployments: https://learn.microsoft.com/azure/ai-services/openai/concepts/models
- Azure OpenAI audio transcription (Whisper): https://learn.microsoft.com/azure/ai-services/openai/whisper-quickstart


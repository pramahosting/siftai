# Test and verification guide

## Automated backend tests

From the pack folder run:

```bat
set PYTHONPATH=%CD%\backend
.venv\Scripts\python.exe -m pytest backend\tests -q
```

Tests cover event eligibility, private/cancelled/all-day exclusions, rendered word counting, VTT timestamp parsing and Sydney daylight-saving day length.

## Frontend build check

With Node.js installed, from `frontend` run:

```bat
npm install
npm run build
```

The Windows demo runs Vite directly. Docker Compose remains available for deployment builds.

## Manual local demo walkthrough

1. Run `app.cmd`; it opens `http://localhost:5173` once the API, local database, worker, and frontend are ready.
2. Confirm Dashboard shows the local administrator and integrations as not configured.
3. Open Meetings; click **Load mock data**.
4. Confirm two fictional meetings appear. No private fixture should be persisted or listed.
5. Open Briefings and click **Preview**. It must say preview only and remain below 250 words.
6. Open Minutes from Product planning. Edit the executive summary JSON and click **Save as reviewed**. Confirm a new reviewed version appears.
7. Open Action items. Change one to In progress and refresh to verify persistence.
8. Open Admin settings. Change a harmless preference and save. Confirm secret status is visible but no value is exposed.
9. Open Run history and confirm the sample run.
10. Stop with `app-stop.cmd`, start again with `app.cmd`, and confirm records remain in `docs/data/meeting_intelligence.db`.

## Integration checks

Use a non-production tenant, test meeting, test Azure OpenAI resource, Neon branch and approved test recipient. Complete the Phase 0 checklist first.

- **Graph calendar:** verify accepted/tentative, paging and permission denial. A private event must not persist or enter AI. A failed/partial Graph call must return an error, never the clear-day message.
- **Official transcript:** create a test meeting with transcription enabled; validate tenant transcript settings, permissions, application access policy when applicable, meeting type and artifact availability. Missing transcript is unavailable, not success.
- **Azure OpenAI audio:** use a test audio file with authorization and consent. Verify job/transcript state and temporary-file deletion when retention is 0. Review provider terms and limits.
- **Minutes:** use a controlled test transcript. Generated minutes stay draft; evidence is retained; uncertain owner/date is not fabricated; reviewer edits create a new version.
- **Power Automate:** configure named Sydney timezone; test at an agreed time; deliver to a test chat; verify callback state and retries. Do not target production before identity/licensing/replay review.
- **Failure email:** trigger a controlled failure and verify the alert has only workflow/safe error data, no meeting content.

## Troubleshooting

- **Browser cannot open:** inspect `app-logs.cmd` and the files in `docs/logs/`. The Windows demo does not use Docker Desktop.
- **Database unavailable:** confirm `docs/data/` is writable and inspect `docs/logs/backend-error.log`.
- **Mock data button missing:** rebuild the frontend with the included demo configuration.
- **Calendar says Graph not configured:** expected until credentials, permissions, user ID and tenant policy are set.
- **Minutes job stays queued:** inspect worker logs and provider setup; sample minutes require no Azure OpenAI credentials.
- **Port in use:** stop the process using localhost ports 5173 or 8000, then rerun `app.cmd`.
- **Permission denied:** have the tenant administrator validate the specific API/scope/policy. Do not add broad permissions without review.


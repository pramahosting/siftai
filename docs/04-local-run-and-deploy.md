# Local run, administration and deployment manual

## What this pack runs

The pack provides a React + TypeScript + Vite web client, a Python/FastAPI API, a durable worker, and Alembic migrations. The Windows local demo uses a persistent SQLite file so it starts without Docker Desktop or a database URL. Connected deployments use PostgreSQL/Neon. Microsoft Entra/Graph, Azure OpenAI (Microsoft Copilot AI), and Power Automate adapters still need organization setup.

Microsoft Teams delivery and the 06:55 weekday recurrence are configured through Power Automate in `power-automate/SETUP.md`. They are not active merely because the app is running. No live meeting capture is implemented. Official transcripts are fetched after a meeting only when Graph access and transcript policy permit it. Audio upload processes an authorized file; it does not join or record a Teams call.

## Windows prerequisites

- Windows 10/11.
- Node.js 18 or later and Python 3.11 or later.
- Internet access on first launch to install package dependencies.
- A browser.

## Start the local demo

1. Extract the full ZIP pack to a writable folder.
2. Double-click `app.cmd`. It creates a private Python environment, installs Python and npm packages on first run, creates the local SQLite database, then starts the API, worker, and Vite frontend. It opens `http://localhost:5173` only after all three processes are running and the API confirms its database is healthy. First launch may take several minutes.
3. Sign in with admin user ID `admin` and password `Meeting$1`. This fixed credential is for single-computer local evaluation only; never expose or deploy demo mode.
4. In **Admin settings**, adjust the Sydney briefing time, lookback window, transcript/minutes retention, and human-review requirement. The local SQLite database is created automatically; startup does not ask for a database URL or other setup values.
5. Open Meetings and select **Load mock data**. The fictional dataset adds two eligible meetings, one transcript with timestamps, draft minutes, two action items and a mock briefing.

Use `app-logs.cmd` to view logs and `app-stop.cmd` to stop the API, worker, and frontend. Stopping preserves `docs/data/meeting_intelligence.db`. To erase local demo records, stop the app and delete that database file.

## Local demo vs connected deployment

Local demo auth is enabled only when `APP_ENV=development`, `AUTH_MODE=local`, `ALLOW_LOCAL_AUTH=true`. Ports bind to localhost. Never expose or deploy demo mode. Before a shared or production deployment:

1. Set `APP_ENV=production`, `AUTH_MODE=entra`, `ALLOW_LOCAL_AUTH=false`.
2. Configure Entra API audience, tenant ID, app roles and redirect URL; set frontend `VITE_ENTRA_*` build arguments.
3. Store client secrets, Azure OpenAI keys, SMTP credentials and automation token in the hosting platform secret manager. Keep `.env` out of source control.
4. Replace local PostgreSQL with a TLS-required Neon connection; verify pool size, region, backups and migration procedure.
5. Review every requested Graph permission and required admin/application access policy.
6. Configure TLS, trusted proxy, rate limiting, network restrictions, backups, alerting and production CORS origin. The provided Compose profile is for local evaluation, not hardened internet-facing deployment.
7. Disable `VITE_DEMO_MODE` and rebuild the frontend before any shared deployment.

See `.env.example` for variable names. Never put secret values in this manual, screenshots or source control.

## Use the app

- **Dashboard:** synced meetings, open actions, briefing status and integration capability.
- **Meetings:** sync connected calendar or load demo data. Generate minutes only after transcript is available.
- **Minutes:** edit structured JSON and save a reviewed version. AI content remains draft until a person reviews it.
- **Action items:** inspect owner/date evidence and update status.
- **Briefings:** create a preview or local manual record. Preview does not send a Teams message. Scheduled runs need Power Automate configuration.
- **Run history:** inspect durable processing jobs.
- **Admin settings:** update app preferences. Secret values are never returned to the UI.

## Mock data

All names and meeting content are fictional. The sample has product planning today at 9:30 AM Sydney time, a security readiness meeting at 11:00 AM, a timestamped transcript, evidence for a Friday checklist decision and two action candidates, an unresolved Finance reporting question, draft minutes and a briefing marked `mock_not_delivered`.

The fixture does not persist a private meeting. The standalone timestamped sample is at `backend/tests/fixtures/sample_meeting.vtt`. A separate policy test verifies that private events are rejected before storage or AI processing.


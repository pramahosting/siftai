# AI Meeting Intelligence Platform

Full implementation pack for Windows local evaluation and organization-specific deployment.

## Quick start (Windows)

1. Extract the ZIP pack to a writable folder.
2. Install Node.js 18+ and Python 3.11+ if they are not already installed.
3. Double-click `app.cmd`. On first launch it installs the app packages, creates a local SQLite database, starts the API, worker, and frontend, and opens the browser when ready.
4. Sign in with admin ID `admin` and password `Meeting$1`, or choose **Sign up** to create your own account (name, email, password). New accounts are regular members; only `admin` (and any email listed in `ADMIN_EMAILS`) can open Admin settings.
5. Open Meetings and choose **Load mock data**.

No Docker Desktop or database URL is needed for the local demo. First launch needs internet access to install Python and npm packages. The SQLite file and logs stay in this extracted folder. Use `app-stop.cmd` to stop the processes and `app-logs.cmd` to inspect logs. Local SQLite is for single-computer evaluation; connected deployments continue to use PostgreSQL/Neon through `DATABASE_URL` and the supplied Docker Compose deployment example.

## Settings

Sign in as admin and open **Admin settings**. Every integration value (Microsoft Copilot AI / Azure OpenAI, Microsoft Entra/Graph, Power Automate, failure email) can be edited there. The current value is shown under each field with its source (saved here, server environment or default). Secrets are encrypted in the database and shown masked. Changes apply immediately to the API and worker, with no restart, and **Reset to default** returns a value to the `.env` setting. The database connection and auth mode stay read-only and are set in the server environment.

## AI service (Microsoft Copilot AI = Azure OpenAI)

Minutes, briefings and audio transcription use **Azure OpenAI in Microsoft Foundry**, the model service behind Microsoft Copilot. (The Microsoft 365 Copilot Chat API is not used: it is beta, works only with a signed-in user's token and cannot run in the unattended worker.)

1. In the Azure portal create an **Azure OpenAI** resource and deploy a chat model that supports structured output (for example `gpt-4o` or `gpt-4.1`). Optionally deploy a **Whisper** model for audio.
2. In **Admin settings → Microsoft Copilot AI** enter the endpoint (`https://<resource>.openai.azure.com`), the chat deployment name, and either the API key or choose *Microsoft Entra app* (give the app registration the **Cognitive Services OpenAI User** role on the resource; it reuses the Microsoft client ID and secret).
3. Save, then use **Test configured connections**. No restart is needed.

The endpoint must be an Azure address (`*.openai.azure.com` or `*.cognitiveservices.azure.com`), so the key can never be sent to another host. If your model is an o-series or GPT-5 reasoning model, turn off *Send temperature 0*.

## Daily calendar refresh

Once Microsoft Graph is configured (Admin settings → Microsoft Entra and Graph), the background worker pulls your calendar automatically: every 30 minutes (change it under Admin settings → Calendar, 0 turns it off) and immediately when the date changes. It covers today and the next 7 days, adds new meetings, updates changed ones, and marks removed or cancelled ones. Private, cancelled and all-day events are never stored. The dashboard's **Today, at a glance** card shows today's meetings, refreshes itself every 5 minutes, and has a **Refresh now** button. The public landing page shows only a dated sample, never anyone's calendar.

## Landing page behaviour

The landing page opens with no sign-in window. Login, Sign up, or clicking any capability tile opens it; from a tile, people without an account are offered **Sign up free** right in the window.

## Folder layout

```
Meeting Intelligence/
  app.cmd  app-stop.cmd  app-logs.cmd   Windows launchers (double-click)
  start-local.ps1  stop-local.ps1       used by the launchers
  .env.example  docker-compose.yml      configuration / Docker example
  README.md  docs/                      manuals, plus runtime docs/data and docs/logs
  backend/                              FastAPI app, worker, tests, alembic migrations
  frontend/                             React web app
```

Runtime folders `docs/data/` (SQLite database, audio, process list) and `docs/logs/` (log files), plus `.venv/`, are created on first launch. Older `data/` and `logs/` folders are moved into `docs/` automatically.

## Included phases

- Phase 0 decision packet and tenant validation checklist.
- Phase 1 API/frontend/database foundation, local and Entra auth modes, admin boundary, migrations.
- Phase 2 deterministic calendar eligibility, Sydney day window, briefing generation/preview and word limit.
- Phase 3 database-backed jobs/retries and Power Automate scheduled-run/delivery callbacks.
- Phase 4 official Graph transcript retrieval and consent-confirmed authorized audio upload with Azure OpenAI (Whisper) transcription.
- Phase 5 typed Azure OpenAI draft minutes (structured JSON output) with evidence fields, versioned human review and action items.
- Phase 6 admin preferences, run/integration health views, retention sweep, deployment/run/test manuals.

## External setup required

The full stack does not mean tenant integrations are pre-authorized or live. Entra app registration, Graph consent/access policy, Neon connection, Azure OpenAI resource and deployments, Power Automate flow, Teams sender identity, SMTP, deployment secret manager, TLS and privacy approval must be configured and tested by the organization. The application displays missing or failed capabilities; it does not claim live capture. No Teams meeting media bot is included.

See:

- `docs/04-local-run-and-deploy.md` — install, operate and configure the app.
- `docs/05-test-guide.md` — automated and manual verification.
- `docs/01-phase0-tenant-checklist.md` — permissions and tenant validation.
- `docs/power-automate/SETUP.md` — weekday 06:55 flow and one-chat delivery route.
- `.env.example` — server-side variable names only.

## Security note

Demo login is a convenience for a single local developer and is not production authentication. Keep `.env` private, configure a production secret manager, set `AUTH_MODE=entra` and disable local auth before deployment. The supplied Docker Compose setup is a starter/evaluation configuration and is not a hardened public-hosting recipe.

## UI update
- Landing page opens first; the sign-in dialog opens only from the top-nav **Login** button.
- Vibrant purple/pink/orange theme; sign-out button in the sidebar.
- `frontend/index.html` now points at `/src/main.tsx`; the API accepts both `localhost:5173` and `127.0.0.1:5173`.

## Multiple users at the same time

Many people can use the app together. Each person signs in with their own account and only ever sees their own meetings, transcripts, minutes, action items and briefings; Admin settings and Run history are for administrators only.

- **Sessions:** each browser tab holds its own sign-in, so different people can be signed in side by side.
- **Calendar:** every person is refreshed from their own mailbox (their sign-in email). The built-in demo `admin` uses the "Calendar user" set in Admin settings. A problem with one person's calendar does not affect anyone else.
- **Database:** the local SQLite file runs in WAL mode so people read while others write; writers wait briefly instead of failing. For a larger group use PostgreSQL (`docker-compose.yml`); set `DB_POOL_SIZE` if needed.
- **Background jobs:** jobs are claimed atomically, so you can run more than one worker without a job being processed twice.
- **Double clicks and parallel requests** (first sign-in in two tabs, sign-up of the same email twice, repeated "Load mock data") are handled without errors.

## Build a compiled copy (single folder of programs)

Run `build.cmd` (Windows) or `./build.sh` (Linux/macOS). It needs Python 3.11+ and Node.js 18+ and an internet connection for the first build. Build on the operating system you want to run on: the Windows build produces `.exe`, and the Linux build does not run on Windows.

The result is `release\MeetingIntelligence\`. Copy that one folder anywhere and double-click `MeetingIntelligence.exe`: it migrates the database, starts the API, the background worker and the web app together, and opens your browser at `http://127.0.0.1:8000/` (next free port if busy). Data and logs go to `docs\data` and `docs\logs` beside the program, and a private sign-in secret is generated on first run. To change settings, copy `.env.example` to `.env` in that folder. The recipe is `backend/meeting_intelligence.spec`; the entry point is `backend/app/standalone.py`.

## Users, mock data and the calendar on this computer

**Users (administrators).** The Users page lists everyone with their role, status, meetings and last sign-in. Administrators can add a user, edit name/role/password, disable or re-enable an account, delete a user (their meetings, transcripts, minutes, actions and briefings are removed too), search, and export the list as CSV. Safeguards: the built-in `admin` account can't be deleted, disabled or demoted; you can't delete, disable or demote yourself; the last active administrator can't be removed. A disabled user is refused at sign-in and on every request. With Microsoft sign-in, people appear after their first sign-in and administrators manage role and status here.

**Mock data.** `docs/mock-data/` has one CSV file per table: users, meetings, transcripts, transcript_segments, minutes, action_items, briefings, workflow_runs, jobs, audit_logs (see its README.txt). *Load mock data* (Dashboard, Meetings or Data import) loads them all; administrators get every file, members get a sample set in their own account. *Reload (replace)* removes earlier mock meetings first. The Data import page also uploads your own CSV for any one table (templates included), with a per-table result and row-level problems. Existing rows are never overwritten. Sample sign-ins use the password `Passw0rd!`. Untick **Allow mock data** in Admin settings to hide the buttons and refuse these requests.

**Calendar on this computer.** When no Microsoft 365 calendar is connected, the app looks for a calendar on the computer it runs on: `.ics` files (in `docs/calendar`, `MACHINE_CALENDAR_DIR`, or the usual Linux/Mac calendar folders) or classic Outlook on Windows. If one is found, the Today card asks the person to **Allow** it; after that it syncs automatically with the normal refresh schedule. Permission is per person and can only be given from the computer itself, never remotely. Administrators can switch the feature off in Admin settings (Calendar). A browser alone can't read a computer's calendar, so the app reads it on the computer where it runs. The Outlook reader and the Mac/Linux folder search could not be tested in the build environment; the `.ics` reader is covered by automated tests.


## First start: sample data and calendar are ready before the app opens

Every start runs a preparation step before the app begins serving (`app/startup.py`; the compiled program and `start-local.ps1` both do it):

1. **Sample data** - the CSV files in `docs/mock-data` are loaded once, the first time (all 10 tables). Later starts say "already loaded".
2. **Calendar** - if a calendar is found on this computer (`.ics` files in `docs/calendar`, or classic Outlook on Windows) it is read for the built-in administrator and synced, so Today, at a glance is filled in on the first screen. Microsoft 365 is used instead when it is configured. Other people are still asked before their calendar is used.

The compiled Windows program runs with no command window; what it did is written to `docs/logs/app.log`. Running from source, the console shows it, for example `Sample data: Added 5 users, 12 meetings...` and `Calendar: synced 9 meeting(s) from machine.` Switch either step off with `LOAD_MOCK_ON_START=false` / `CALENDAR_ON_START=false` in `.env`, or in Admin settings under Startup (applies at the next start). To load the sample data again, use Data import > Reload (replace).

**Minutes, transcripts and briefings.** Minutes are shown as a readable page (summary, agenda, what was discussed, decisions with who and evidence, action items, open questions); *Edit* uses plain boxes, *Save as reviewed* keeps older versions collapsed, and *Copy as text* gives plain text. The Transcripts page lists meetings that have a transcript and shows the selected one speaker by speaker with times, search and copy; meetings without one offer *Fetch official transcript* or *Upload audio*. The morning briefing starts with an overview paragraph, then lists each meeting with its time range and preparation points (under 400 words).


**Compiled program on Windows.** Double-click `MeetingIntelligence.exe`: no command window appears, the app runs in the background and your browser opens. Double-clicking again just reopens the page (it never starts a second copy). To stop it, run `Stop Meeting Intelligence.cmd` in the same folder. If it cannot start, a message box says why and the details are in `docs/logs/app.log`.

**Finding your calendar.** The app searches for `.ics` calendar files in `docs/calendar`, Downloads, Documents, Desktop and OneDrive (up to three folders deep; only real calendar files are used), and for classic Outlook if it already has an account. Dashboard > *Search this computer again* repeats the search, and *Upload .ics file* lets anyone pick a file directly (it is kept private to that account and replaced by the next upload). Meetings in the next 7 days are added, and recurring events are expanded.

**Connections, Zoom and new meetings.** *Connections* (every user) adds calendars by their private link: Google/Gmail, Yahoo, Outlook.com, iCloud or any .ics/webcal link (stored encrypted, fetched only from public https addresses, refreshed automatically) or an uploaded .ics file. Zoom, Teams, Google Meet and Webex links inside events become *Join* buttons. *New meeting* on the Meetings page schedules a meeting, optionally creating a real Zoom meeting. Administrators set Zoom up in Admin settings > Zoom (Server-to-Server OAuth: account ID, client ID, client secret; scopes meeting:read, meeting:write, cloud_recording:read, user:read); after a Zoom meeting, *Fetch official transcript* reads Zoom's cloud-recording transcript (turn on cloud recording with audio transcript in Zoom). Email reading and our own audio/video rooms are discussed in docs/08-zoom-like-meetings-review.md.

**Meeting rooms (built-in video).** *Meetings > Start meeting now* (or *Schedule meeting* > Built-in video meeting) opens a room with camera, microphone, screen sharing, chat and a participant list. *Invite* copies the link; guests open it in any browser and join with just a name. The host can remove people, end the meeting for everyone and press *Record*: everyone sees a red Recording banner, the audio is saved for the transcript (sent to the transcription model if one is configured in Admin settings, then minutes work as usual) and a video recording is kept under *Meeting recordings* on the Meetings page for download or deletion. Rooms connect browsers directly (about 8 people); set STUN/TURN servers in Admin settings > Video meetings (a TURN server is needed for people behind strict firewalls). Keep the host's browser tab open and visible while recording. Camera and microphone need https or http://127.0.0.1/localhost, so to let other computers join, serve the app over https (for example behind a reverse proxy).

**Calendars, mail and Outlook.** *Connections > Add a calendar account*: type the email address and the page chooses the method: private link (Google/Gmail, Outlook.com, Microsoft 365 published calendars, iCloud) or CalDAV with an app password (Yahoo, iCloud, Fastmail, other). *Your mail account* (Gmail, Yahoo, Outlook.com, iCloud or any SMTP/IMAP server, with an app password) sends invitations from *Schedule meeting > Invite people* as normal calendar invitations, and can add invitations found in your inbox to your calendar (read-only, mail is not stored or marked as read). Classic Outlook on Windows is read automatically for every account set up in it, but only if it already has an account. The *new* Outlook for Windows does not allow other programs to read its accounts, passwords or calendars, so add each account on this page (about a minute each).

## Settings needed to run it
See [docs/SETUP.md](docs/SETUP.md). In short: change the administrator password (`LOCAL_ADMIN_PASSWORD`), add Azure OpenAI details in Admin settings, and for use from other computers set `MI_LISTEN=lan` (https, needed for camera and microphone) and open the port in the firewall. Admin settings starts with a live **Setup checklist** showing what is still missing.

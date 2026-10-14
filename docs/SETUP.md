# Settings needed to run Meeting Intelligence

Everything below can be set in **Admin settings**, which has three tabs: **Run the app** (AI, sample data, defaults), **Email and calendar**, and **Meeting platforms** (Teams, Zoom, Google Meet, built-in video). No restart is needed except the items marked *.env*, which are read at start-up. The top of Admin settings shows a live **Setup checklist** of what is still missing.

## 1. Minimum to start (nothing to configure)
Windows: double-click `app.cmd` (or the compiled `MeetingIntelligence.exe`). It opens in your browser at http://localhost:8000. Sample data loads on first start. Sign in as `admin` / `Meeting$1`.

## 2. Do these before real use
| Setting | Where | Why |
|---|---|---|
| Administrator password | *.env* `LOCAL_ADMIN_PASSWORD=...` | The sample password is public. In network mode a random one is created in `docs/data/admin-password.txt`. |
| Azure OpenAI endpoint, key, chat deployment | Admin settings > Microsoft Copilot AI | Needed for minutes, action items and briefings. |
| Transcription (Whisper) deployment | same group | Needed to transcribe recorded meetings and uploaded audio. |
| Mock data off | Admin settings > Mock data | Hides sample data and CSV loading in production. |

## 3. Calendars and mail (per person, under Connections)
- **Gmail**: Google Calendar > Settings > your calendar > *Secret address in iCal format*, paste as a calendar link. For mail/invites use an *app password* (needs 2-step verification).
- **Yahoo / iCloud / Fastmail**: choose CalDAV and enter an *app password* from the provider's security page.
- **Outlook.com / Microsoft 365**: publish the calendar and paste the ICS link, or an administrator sets up Microsoft Graph (Admin settings > Microsoft Entra and Graph).
- **Classic Outlook on Windows** is read automatically after the person allows it. The *new* Outlook cannot be read by any program; use the calendar link or the Add-by-email helper for its accounts.
- Anyone can also drop `.ics` files into `docs/calendar` or upload one.

## 4. Zoom (optional)
Zoom Marketplace > Develop > Build App > **Server-to-Server OAuth**. Add scopes `meeting:read:admin`, `meeting:write:admin`, `cloud_recording:read:admin`, `user:read:admin`. Copy Account ID, Client ID and Secret into Admin settings > Zoom, then press Test on the Connections page.

## 5. Built-in video meetings
- Camera/microphone only work on `https://` or `localhost`. For other computers set in *.env*: `MI_LISTEN=lan` (https + reachable on the network). Browsers show a certificate warning once for the self-signed certificate; use a real certificate behind a reverse proxy for a clean experience.
- Open the app port (default 8000) in Windows Firewall for LAN use.
- Add a **TURN server** (Admin settings > Video meetings) for people on strict networks or mobile data.
- **Who can join** (set per meeting when scheduling, changeable by the host in the room under *Security*; the defaults are in Admin settings > Video meetings): anyone with the link, link plus passcode, or signed-in people only. A **waiting room** (host admits people) is on by default. People can also type a meeting ID or paste a link into the **Join** box on the home page or Meetings page.
- Room size defaults to 25 people (maximum 100). Video quality is best up to about 8 cameras because each browser connects to every other; larger meetings should keep most cameras off.
- Recording: the host's browser records, and may stay in the background but must not be closed (a warning appears).

## 6. Optional
Failure emails (SMTP), Power Automate token, retention periods, automatic calendar refresh interval, `DATABASE_URL` for PostgreSQL instead of the local SQLite file, and regular copies of `docs/data` (database and recordings) as a backup.

## Not included
Google and Microsoft "Sign in" buttons (OAuth) are not built; they need an app registered in your own Google/Microsoft account. The links/app-password methods above cover the same calendars.

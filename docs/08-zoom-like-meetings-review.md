# Review: can we build Zoom-style scheduling, audio/video and recording?

Short answer: **yes, but build it on a media service, not from scratch.** Scheduling and organising meetings is easy and low-risk. Live audio/video is a different kind of software (real-time networking), and the sensible route is to rent or self-host the hard part and keep this app as the "intelligence" layer (calendar, transcripts, minutes, actions) it already is.

## Update: what has now been built
The built-in meeting rooms (camera, microphone, screen share, chat, host controls, recording to transcript), CalDAV calendars, a personal mail account for invitations and inbox invitations, and Outlook detection are now in the app (see README, 'Meeting rooms' and 'Connections'). Built-in rooms are peer-to-peer (everyone connects to everyone), which suits about 8 people; larger meetings or very strict networks need a media server (LiveKit) and a TURN server, as described below. Gmail/Google OAuth sign-in is still not built: Google calendars use the private link, Gmail mail uses an app password.

## What the app did before this update
| Need | Status |
|---|---|
| Calendars from Google/Gmail, Yahoo, Outlook.com, iCloud | **Done through each calendar's private .ics link** (Connections page), plus .ics upload and the computer's own calendar |
| Join buttons for Zoom, Teams, Google Meet, Webex | **Done** - links are recognised in the event |
| Create a Zoom meeting from the app | **Done** (Admin settings > Zoom, Server-to-Server OAuth); tested with simulated Zoom answers only - needs a real Zoom account to confirm |
| Zoom official transcript into minutes | **Done** (reads the cloud-recording transcript after the meeting) - same caveat |
| Read Gmail / Yahoo *email* | Not built (see Phase 2) |
| Our own audio/video meetings and recording | Not built (see Phase 3) |

## The three ways to get live meetings

**A. Integrate (what we do now).** Zoom/Teams/Meet run the call; we schedule, link, fetch transcripts and make minutes. Cost: near zero, risk: low, time: done. Limit: no recording unless the host turns on the vendor's cloud recording.

**B. Build on a media platform (recommended if you want your own meeting rooms).**
- *LiveKit* (open source, self-host or cloud): rooms, screen share, server-side recording ("Egress") to MP4 in your storage, SDKs for browser/mobile. Closest to "build our own Zoom" with least work.
- *Jitsi* (open source, self-host, or 8x8 JaaS): quickest to a working room; recording through Jibri; less control over the UI.
- *Azure Communication Services* (Microsoft): fits an Azure/Entra estate, has call recording and can join Teams meetings; pay per minute.
- *Daily, Twilio Video, Agora, Amazon Chime SDK*: managed APIs, pay per participant-minute.

**C. Write it ourselves (not recommended).** WebRTC needs an SFU (selective forwarding unit) once there are more than ~4 people, TURN servers for firewalls, congestion control, echo cancellation, mobile quirks and 24/7 operations. It is months of specialist work and ongoing cost for no business advantage.

## Recording and transcription design (for option B)
1. **Capture:** server-side composite recording (one MP4) plus separate audio tracks per speaker. Browser-side recording (MediaRecorder) is unreliable and stops if the tab closes.
2. **Storage:** private object storage (Azure Blob / S3), encrypted, one folder per tenant, retention rules (the app already has retention settings for transcripts/minutes - extend them to recordings).
3. **Transcription:** use per-speaker audio tracks or a service with speaker labels (Azure AI Speech batch transcription with diarization, or Azure OpenAI transcription plus per-track audio). Whisper alone does not label speakers.
4. **Pipeline:** recording finished -> job `transcribe_recording` -> transcript saved -> existing `generate_minutes` job. The worker, transcript viewer, minutes and action items already exist; only the first step is new.
5. **Consent and law:** show a clear "this meeting is being recorded" notice to every participant, require the host to switch recording on, and record who consented. In Australia recording a private conversation generally needs the consent of the participants (state surveillance-devices laws differ). Have your legal team confirm the wording and retention before going live. The current app already asks for a consent confirmation on audio upload; reuse that pattern.

## Scheduling and organising (low risk, do first)
- Meeting model additions: attendees (email, RSVP), recurrence, time zone, agenda, passcode, waiting room, host/co-host roles.
- Send invitations as standard calendar invites (.ics attachment by SMTP, or through Microsoft Graph / Gmail API) so they land in Outlook, Gmail and Yahoo calendars with the join link.
- Write-back: create the event in the person's own calendar (Graph or Google Calendar API) so it appears everywhere.
- Reminders and "open the room" button 5 minutes before.

## Suggested phases
| Phase | What | Rough effort |
|---|---|---|
| 1 (this release) | Calendar links, join buttons, Zoom create + transcripts, new-meeting form | done |
| 2 | Google/Microsoft OAuth (replaces private links, lets us read mail context and write invites), CalDAV for Yahoo/iCloud, attendee invitations with .ics | 2-3 weeks |
| 3 | Own rooms on LiveKit or Azure Communication Services: lobby, camera/mic, screen share, host controls, recording, transcript pipeline | 4-8 weeks |
| 4 | Hardening: TURN/network testing, load test, retention, audit, accessibility, mobile | 3-4 weeks |

## Decision to make
Do you need **our own** meeting rooms, or do you need meetings on Zoom/Teams/Meet to be *organised, recorded-with-consent and turned into minutes*? If the second, Phases 1-2 deliver almost all the value. Choose Phase 3 only if there is a firm reason to own the call (branding, data residency, embedding in another product, per-seat cost at scale).

## Update: limits removed
Meeting size now defaults to 25 people (configurable to 100), recording continues while the host's tab is in the background (with a warning before closing), and network/https mode (`MI_LISTEN=lan`) lets other computers join with camera and microphone. Browser/physical limits remain: very large meetings need a media server (SFU), and strict networks need a TURN server. Google/Microsoft OAuth sign-in buttons were not built. See docs/SETUP.md.

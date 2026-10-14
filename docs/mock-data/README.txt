Mock data for Meeting Intelligence (one CSV file per table)
===========================================================
Load everything with one click: Dashboard or Meetings -> "Load mock data", or the "Data import" page.
Upload your own file for one table on the "Data import" page (download a template there first).

Files, in load order: users, meetings, transcripts, transcript_segments, minutes, action_items, briefings, workflow_runs, jobs, audit_logs.
(Sign-in accounts are part of users.csv. Integration settings and secrets are never imported - use Admin settings.)

How rows link together (no internal ids needed)
  owner_email           the person who owns the row (blank = you; members always load into their own account)
  meeting_external_id   links to meetings.csv external_id (same owner)
  ref / transcript_ref  links transcript_segments to transcripts

Dates: ISO (2026-10-14 09:30) or relative words: today 09:30, tomorrow 14:00, yesterday 15:00, +2d 10:00, -3d 11:00.
Existing rows are never overwritten: rows that already exist are skipped and counted.
Mock meeting ids start with "demo-"; "Reload (replace)" removes those first and loads fresh copies.

Who gets what
  Admin       loads every file. Rows owned by admin@example.test go to the signed-in admin; other owners must exist
              (users.csv creates them, password for all sample users: Passw0rd!). ben.carter is created disabled.
  Member      loads only the rows owned by sample.user@example.com, copied into their own account.
Admin-only tables: users, workflow_runs, jobs, audit_logs.
Mock jobs must be completed/failed (they never run). Audit logs are never deleted by Reload.

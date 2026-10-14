Calendar files (.ics)
---------------------
Meeting Intelligence can read the calendar of the computer it runs on, after each person allows it
(Dashboard -> "Calendar found on this computer" -> Allow). An administrator can switch this off in
Admin settings -> Calendar.

Sources it looks for, in this order:
  1. .ics files in this folder (docs\calendar), in the folder set by MACHINE_CALENDAR_DIR, and in
     the usual desktop calendar folders (Evolution on Linux; Calendar on Mac when file access is granted).
     Export or subscribe to your calendar as .ics and drop the file here (Google Calendar, Outlook.com,
     Apple Calendar and most others can export .ics).
  2. Classic Microsoft Outlook on Windows (read directly; Outlook opens if it is closed).
     The "new Outlook" and the Windows Calendar app cannot be read this way - export an .ics instead.

Daily, weekly, monthly and yearly repeats, exceptions, private and cancelled events are handled.
Private, cancelled and all-day events are skipped, like everywhere else in the app.
Only the computer running the app can allow this; people using the app from another computer cannot.
Microsoft 365 (Admin settings -> Microsoft Entra and Graph) is used first when it is configured.

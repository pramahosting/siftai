"""Read the calendar of the computer this app runs on (only after the person has allowed it).

Sources, first one found wins:
  1. .ics files    - a folder you choose (MACHINE_CALENDAR_DIR), docs/calendar next to the app, and the usual
                     desktop calendar folders (Evolution on Linux, Calendar on macOS when it grants file access).
  2. Outlook       - classic desktop Outlook on Windows (through its built-in automation interface; Outlook opens if it is closed).
Events are returned in the same shape as Microsoft Graph events so the rest of the app treats them identically.
"""
import asyncio, base64, json, logging, os, re, sys
from datetime import datetime, timedelta, timezone, date, time
from pathlib import Path
from zoneinfo import ZoneInfo
from app.core.config import settings

log = logging.getLogger("meeting_platform")
MAX_ICS_BYTES = 20 * 1024 * 1024

class MachineCalendarError(RuntimeError): pass

_LAST: dict = {"accounts": []}   # accounts seen on the last Outlook read

_SKIP = {"node_modules", "appdata", "windows", "program files", "program files (x86)", "$recycle.bin", ".git", "library", "site-packages"}
_cache: dict = {"at": 0.0, "files": []}

def ics_folders() -> list[Path]:
    """Folders searched for calendar files: the one you configured, docs/calendar, and the places people usually save exports."""
    from app.services.datasets import mock_dir
    out = []
    if settings.machine_calendar_dir: out.append(Path(settings.machine_calendar_dir))
    out.append(mock_dir().parent / "calendar")
    home = Path.home()
    for env in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        if os.environ.get(env): out.append(Path(os.environ[env]))
    out += [home / "Downloads", home / "Documents", home / "Desktop", home / "Documents" / "Outlook Files",
            home / ".local/share/evolution/calendar", home / "Library/Calendars"]
    try: out += [p for p in home.glob("OneDrive*") if p.is_dir()]
    except OSError: pass
    seen, uniq = set(), []
    for p in out:
        try: key = str(p.resolve())
        except OSError: continue
        if key not in seen and p.is_dir(): seen.add(key); uniq.append(p)
    return uniq

def _looks_like_calendar(f: Path) -> bool:
    try:
        with open(f, "rb") as fh: head = fh.read(4096).upper()
        return b"BEGIN:VCALENDAR" in head
    except OSError: return False

def _scan(folder: Path, max_depth: int = 3) -> list[Path]:
    found, base = [], len(folder.parts)
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d.lower() not in _SKIP and not d.startswith(".")] if len(Path(root).parts) - base < max_depth else []
        for n in names:
            if n.lower().endswith((".ics", ".ical", ".icsevent")):
                f = Path(root) / n
                try:
                    if f.stat().st_size <= MAX_ICS_BYTES and _looks_like_calendar(f): found.append(f)
                except OSError: continue
        if len(found) >= 500: break
    return found

def _ics_files(refresh: bool = False) -> list[Path]:
    import time
    if not refresh and time.time() - _cache["at"] < 60: return _cache["files"]
    files = []
    for folder in ics_folders():
        try: files += _scan(folder)
        except OSError: continue
    _cache.update(at=time.time(), files=files[:500])
    return _cache["files"]

def _outlook_has_profile() -> bool:
    """True only when Outlook already has a mail profile. Without one, starting Outlook would pop up its
    'Add Account' wizard and wait for a person, so the app must not start it."""
    try:
        import winreg
        for ver in ("16.0", "15.0", "14.0"):
            for sub in (rf"Software\Microsoft\Office\{ver}\Outlook\Profiles", rf"Software\Microsoft\Windows NT\CurrentVersion\Windows Messaging Subsystem\Profiles"):
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as k:
                        for i in range(winreg.QueryInfoKey(k)[0]):
                            with winreg.OpenKey(k, winreg.EnumKey(k, i)) as prof:
                                if winreg.QueryInfoKey(prof)[0] > 0: return True      # a profile with content (accounts)
                except OSError: continue
    except ImportError: pass
    return False

def _outlook_installed() -> bool:
    if sys.platform != "win32": return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Outlook.Application\CLSID"))
    except OSError: return False
    return _outlook_has_profile()

def new_outlook_present() -> bool:
    """The 'new Outlook for Windows' (a web-based app). Unlike classic Outlook it cannot be read by other programs."""
    if sys.platform != "win32": return False
    base = os.environ.get("LOCALAPPDATA", "")
    if not base: return False
    try: return any(Path(base, "Packages").glob("Microsoft.OutlookForWindows_*")) or Path(base, "Microsoft", "Olk").is_dir()
    except OSError: return False

NEW_OUTLOOK_NOTE = ("Your Outlook is the new Outlook for Windows, which does not let other programs read its accounts, passwords or calendars. "
                    "Use 'Add an account by email address' below (one minute per account), or switch Outlook back to classic Outlook with your accounts added there.")

def outlook_classic_installed() -> bool:
    if sys.platform != "win32": return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Outlook.Application\CLSID")); return True
    except OSError: return False

def detect(refresh: bool = False) -> dict:
    files = _ics_files(refresh)
    if files: return {"available": True, "kind": "ics", "source": f"calendar files on this computer ({len(files)} found)"}
    if _outlook_installed(): return {"available": True, "kind": "outlook", "source": "classic Outlook on this computer (every account set up in it)"}
    note = None
    if outlook_classic_installed() and not _outlook_has_profile():
        note = ("Classic Outlook is installed but has no email account set up, so it was left alone. " + (NEW_OUTLOOK_NOTE if new_outlook_present() else "Add your accounts in classic Outlook (File > Add Account) and this app will read all of them."))
    elif new_outlook_present(): note = NEW_OUTLOOK_NOTE
    return {"available": False, "kind": None, "source": None, "note": note}

# ---------------- ICS ----------------
def _unfold(text: str) -> list[str]:
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines: lines[-1] += raw[1:]
        else: lines.append(raw)
    return lines

def _prop(line: str):
    head, _, value = line.partition(":")
    parts = head.split(";"); params = {}
    for p in parts[1:]:
        k, _, v = p.partition("="); params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value

def _local_tz():
    return datetime.now().astimezone().tzinfo or timezone.utc

def _dt(value: str, params: dict):
    """Returns (aware datetime, all_day)."""
    v = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", v):
        d = date(int(v[:4]), int(v[4:6]), int(v[6:8])); return datetime.combine(d, time.min, tzinfo=_local_tz()), True
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)", v)
    if not m: raise ValueError("bad date")
    y, mo, d, h, mi, s = (int(x) for x in m.groups()[:6])
    if m.group(7): tz = timezone.utc
    else:
        try: tz = ZoneInfo(params["TZID"]) if params.get("TZID") else _local_tz()
        except Exception: tz = _local_tz()      # e.g. Windows zone names: fall back to this computer's zone
    return datetime(y, mo, d, h, mi, s, tzinfo=tz), False

def parse_ics(text: str) -> list[dict]:
    events, cur = [], None
    for line in _unfold(text):
        if line.upper() == "BEGIN:VEVENT": cur = {"exdates": []}; continue
        if line.upper() == "END:VEVENT":
            if cur is not None and "start" in cur: events.append(cur)
            cur = None; continue
        if cur is None or ":" not in line: continue
        name, params, value = _prop(line)
        try:
            if name == "DTSTART": cur["start"], cur["all_day"] = _dt(value, params)
            elif name == "DTEND": cur["end"], _ = _dt(value, params)
            elif name == "DURATION":
                m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", value.strip())
                if m: cur["duration"] = timedelta(days=int(m.group(1) or 0), hours=int(m.group(2) or 0), minutes=int(m.group(3) or 0))
            elif name == "EXDATE":
                for part in value.split(","): cur["exdates"].append(_dt(part, params)[0])
            elif name == "RRULE": cur["rrule"] = dict(kv.split("=", 1) for kv in value.split(";") if "=" in kv)
            elif name == "SUMMARY": cur["summary"] = value.replace("\\,", ",").replace("\\n", " ").replace("\\;", ";")
            elif name == "UID": cur["uid"] = value
            elif name == "CLASS": cur["class"] = value.upper()
            elif name == "STATUS": cur["status"] = value.upper()
            elif name == "LOCATION": cur["location"] = value.replace("\\,", ",")
            elif name == "DESCRIPTION": cur["description"] = value
            elif name == "URL": cur["url"] = value
            elif name == "X-GOOGLE-CONFERENCE": cur["conference"] = value
            elif name == "X-MICROSOFT-SKYPETEAMSMEETINGURL": cur["conference"] = value
            elif name == "ORGANIZER": cur["organizer"] = re.sub(r"(?i)^mailto:", "", value)
            elif name == "RECURRENCE-ID": cur["recurrence_id"] = _dt(value, params)[0]
        except (ValueError, KeyError): continue
    return events

_DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

def _occurrences(ev: dict, win_start: datetime, win_end: datetime):
    start = ev["start"]; dur = (ev["end"] - start) if "end" in ev else ev.get("duration", timedelta(hours=1))
    rule = ev.get("rrule")
    if not rule:
        if start < win_end and start + dur > win_start: yield start, start + dur
        return
    freq = rule.get("FREQ", ""); interval = max(1, int(rule.get("INTERVAL", "1") or 1)); count = int(rule["COUNT"]) if rule.get("COUNT", "").isdigit() else None
    until = None
    if rule.get("UNTIL"):
        try: until = _dt(rule["UNTIL"], {})[0]
        except ValueError: pass
    byday = [(_DAYS[d[-2:]]) for d in rule.get("BYDAY", "").split(",") if d[-2:] in _DAYS] if freq == "WEEKLY" else []
    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"): freq = ""
    if not freq:
        if start < win_end and start + dur > win_start: yield start, start + dur
        return
    ex = {e.astimezone(timezone.utc) for e in ev["exdates"]}
    n = 0; d = start.date(); end_day = win_end.date() + timedelta(days=1)
    for _ in range(30000):
        if d > end_day: break
        hit = False
        if freq == "DAILY": hit = ((d - start.date()).days % interval == 0)
        elif freq == "WEEKLY":
            wk = ((d - start.date()).days + start.weekday()) // 7
            hit = wk % interval == 0 and (d.weekday() in byday if byday else d.weekday() == start.weekday())
        elif freq == "MONTHLY": hit = d.day == start.day and ((d.year - start.year) * 12 + d.month - start.month) % interval == 0
        else: hit = d.month == start.month and d.day == start.day and (d.year - start.year) % interval == 0
        if hit:
            occ = datetime.combine(d, start.timetz().replace(tzinfo=None), tzinfo=start.tzinfo)
            if until and occ > until: break
            n += 1
            if count and n > count: break
            if occ.astimezone(timezone.utc) not in ex and occ < win_end and occ + dur > win_start: yield occ, occ + dur
        d += timedelta(days=1)

def _graph_shape(ev: dict, s: datetime, e: datetime, recurring: bool) -> dict:
    f = lambda x: x.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000")
    cls = ev.get("class", "PUBLIC"); sens = {"PRIVATE": "private", "CONFIDENTIAL": "confidential"}.get(cls, "normal")
    uid = ev.get("uid") or ev.get("summary", "event")
    from app.services.meeting_links import find_join_url
    join = find_join_url(ev.get("conference"), ev.get("url"), ev.get("location"), ev.get("description"))
    return {"id": f"ics:{uid}:{f(s)}" if recurring else f"ics:{uid}", "subject": ev.get("summary") or "Meeting", "sensitivity": sens,
            "onlineMeetingUrl": join, "isCancelled": ev.get("status") == "CANCELLED", "isAllDay": bool(ev.get("all_day")),
            "responseStatus": {"response": "tentativelyAccepted" if ev.get("status") == "TENTATIVE" else "accepted"},
            "start": {"dateTime": f(s)}, "end": {"dateTime": f(e)}, "organizer": {"emailAddress": {"address": ev.get("organizer", "")}}}

def events_from_ics_text(text: str, win_start: datetime, win_end: datetime) -> list[dict]:
    parsed = parse_ics(text); overridden = {(e.get("uid"), e["recurrence_id"].astimezone(timezone.utc)) for e in parsed if "recurrence_id" in e}
    out = []
    for ev in parsed:
        for s, e in _occurrences(ev, win_start, win_end):
            if "recurrence_id" not in ev and (ev.get("uid"), s.astimezone(timezone.utc)) in overridden: continue
            out.append(_graph_shape(ev, s, e, bool(ev.get("rrule"))))
    return out

# ---------------- Outlook (Windows) ----------------
_PS = r"""
$ErrorActionPreference = 'Stop'
$ol = New-Object -ComObject Outlook.Application
$ns = $ol.GetNamespace('MAPI')
$s = [datetime]::Parse('__START__', [Globalization.CultureInfo]::InvariantCulture)
$e = [datetime]::Parse('__END__', [Globalization.CultureInfo]::InvariantCulture)
$filter = "[Start] >= '" + $s.ToString('g') + "' AND [Start] <= '" + $e.ToString('g') + "'"
$list = New-Object System.Collections.ArrayList
$seen = @{}
$accounts = @(); foreach ($a in $ns.Accounts) { try { $accounts += [string]$a.SmtpAddress } catch {} }
foreach ($store in $ns.Stores) {
  try { $cal = $store.GetDefaultFolder(9) } catch { continue }
  try {
    $items = $cal.Items; $items.IncludeRecurrences = $true; $items.Sort('[Start]')
    foreach ($i in $items.Restrict($filter)) {
      $key = ($i.GlobalAppointmentID + '|' + $i.Start.Ticks)
      if ($seen.ContainsKey($key)) { continue }; $seen[$key] = 1
      [void]$list.Add([ordered]@{
        id = $key; subject = [string]$i.Subject; account = [string]$store.DisplayName
        start = $i.Start.ToUniversalTime().ToString('o'); end = $i.End.ToUniversalTime().ToString('o')
        allDay = [bool]$i.AllDayEvent; sensitivity = [int]$i.Sensitivity; meetingStatus = [int]$i.MeetingStatus
        organizer = [string]$i.Organizer; response = [int]$i.ResponseStatus; body = [string]$i.Location + ' ' + [string]$i.Body })
    }
  } catch { continue }
}
ConvertTo-Json -InputObject ([ordered]@{ accounts = @($accounts); events = @($list) }) -Compress -Depth 4
"""

async def _outlook_events(win_start: datetime, win_end: datetime) -> list[dict]:
    script = _PS.replace("__START__", win_start.astimezone().strftime("%Y-%m-%d %H:%M:%S")).replace("__END__", win_end.astimezone().strftime("%Y-%m-%d %H:%M:%S"))
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    try:
        proc = await asyncio.create_subprocess_exec("powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                    creationflags=0x08000000)  # CREATE_NO_WINDOW: no flashing console
        out, err = await asyncio.wait_for(proc.communicate(), timeout=40)
    except (FileNotFoundError, asyncio.TimeoutError) as exc:
        if isinstance(exc, asyncio.TimeoutError):
            try: proc.kill(); await proc.wait()          # do not leave a stuck PowerShell behind
            except Exception: pass
        raise MachineCalendarError("Outlook did not respond. Make sure classic Outlook is installed and not waiting on a prompt.")
    if proc.returncode != 0:
        log.warning("Outlook read failed: %s", err.decode(errors="ignore")[:300])
        raise MachineCalendarError("Outlook could not be read. Open Outlook once, then try again.")
    text = out.decode("utf-8-sig", errors="ignore").strip()
    try: data = json.loads(text) if text else {}
    except json.JSONDecodeError: raise MachineCalendarError("Outlook returned data that could not be read.")
    rows = data.get("events", []) if isinstance(data, dict) else (data or [])
    if isinstance(rows, dict): rows = [rows]
    _LAST["accounts"] = data.get("accounts", []) if isinstance(data, dict) else []
    resp_map = {0: "accepted", 1: "accepted", 2: "tentativelyAccepted", 3: "accepted", 4: "declined", 5: "notResponded"}
    sens_map = {1: "personal", 2: "private", 3: "confidential"}
    f = lambda iso: datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000")
    return [{"id": "outlook:" + r["id"], "subject": r.get("subject") or "Meeting", "sensitivity": sens_map.get(r.get("sensitivity"), "normal"),
             "isCancelled": r.get("meetingStatus") in (5, 7), "isAllDay": bool(r.get("allDay")),
             "responseStatus": {"response": resp_map.get(r.get("response"), "accepted")}, "start": {"dateTime": f(r["start"])}, "end": {"dateTime": f(r["end"])},
             "onlineMeetingUrl": __import__("app.services.meeting_links", fromlist=["find_join_url"]).find_join_url(r.get("body")),
             "organizer": {"emailAddress": {"address": r.get("organizer", "")}}} for r in rows]

async def fetch(win_start: datetime, win_end: datetime) -> list[dict]:
    info = detect()
    if not info["available"]: raise MachineCalendarError("No calendar was found on this computer.")
    if info["kind"] == "outlook": return await _outlook_events(win_start, win_end)
    events = []
    for f in _ics_files(True):
        try:
            if f.stat().st_size > MAX_ICS_BYTES: continue
            events += events_from_ics_text(f.read_text(encoding="utf-8", errors="ignore"), win_start, win_end)
        except OSError: continue
    seen, uniq = set(), []
    for e in events:
        if e["id"] in seen: continue
        seen.add(e["id"]); uniq.append(e)
    return uniq

"""Build a standard calendar invitation (.ics, METHOD:REQUEST) so it lands in Outlook, Gmail, Yahoo and Apple Calendar."""
import re
from datetime import datetime, timezone

EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")

def parse_recipients(raw: str) -> list[str]:
    out, seen = [], set()
    for p in re.split(r"[,;\s]+", raw or ""):
        p = p.strip().lower()
        if p and p not in seen:
            if not EMAIL.match(p): raise ValueError(f"'{p}' is not a valid email address.")
            seen.add(p); out.append(p)
    if len(out) > 50: raise ValueError("You can invite up to 50 people at once.")
    return out

def _esc(t: str) -> str: return t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
def _fold(line: str) -> str:
    b = line.encode(); parts = []
    while len(b) > 74:
        cut = 74
        while cut > 0 and (b[cut] & 0xC0) == 0x80: cut -= 1
        parts.append(b[:cut].decode()); b = b[cut:]
    parts.append(b.decode()); return "\r\n ".join(parts)

def build_ics(uid: str, title: str, start: datetime, end: datetime, organizer: str, attendees: list[str], join_url: str | None, agenda: str = "") -> bytes:
    f = lambda d: d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    desc = (agenda + "\n\n" if agenda else "") + (f"Join: {join_url}" if join_url else "")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Meeting Intelligence//EN", "CALSCALE:GREGORIAN", "METHOD:REQUEST", "BEGIN:VEVENT", f"UID:{uid}@meeting-intelligence",
             f"DTSTAMP:{f(datetime.now(timezone.utc))}", f"DTSTART:{f(start)}", f"DTEND:{f(end)}", f"SUMMARY:{_esc(title)}", f"ORGANIZER:mailto:{organizer}"]
    lines += [f"ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:{a}" for a in attendees]
    if desc.strip(): lines.append(f"DESCRIPTION:{_esc(desc)}")
    if join_url: lines += [f"LOCATION:{_esc(join_url)}", f"URL:{join_url}"]
    lines += ["STATUS:CONFIRMED", "SEQUENCE:0", "END:VEVENT", "END:VCALENDAR"]
    return ("\r\n".join(_fold(l) for l in lines) + "\r\n").encode()

"""Recognise online-meeting links (Zoom, Teams, Google Meet, Webex) in calendar events."""
import re
from urllib.parse import urlsplit

_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
_HOSTS = (  # (provider, host suffixes)
    ("zoom", (".zoom.us", ".zoomgov.com", "zoom.us")),
    ("teams", ("teams.microsoft.com", "teams.live.com")),
    ("meet", ("meet.google.com",)),
    ("webex", (".webex.com", "webex.com")),
)
LABELS = {"room": "Meeting room", "zoom": "Zoom", "teams": "Teams", "meet": "Google Meet", "webex": "Webex"}

def provider_for(url: str | None) -> str | None:
    if not url: return None
    try: parts = urlsplit(url); host = (parts.hostname or "").lower()
    except ValueError: return None
    if parts.fragment.startswith("/room/"): return "room"        # built-in meeting room of this app
    for name, suffixes in _HOSTS:
        if any(host == s.lstrip(".") or host.endswith(s if s.startswith(".") else "." + s) for s in suffixes): return name
    return None

def find_join_url(*texts: str | None) -> str | None:
    """First meeting link found in the given texts (URL, location, description...)."""
    for t in texts:
        for u in _URL.findall((t or "").replace("\\n", " ").replace("\\,", ",")):
            u = u.rstrip(".,;")
            if provider_for(u): return u
    return None

def zoom_meeting_id(url: str | None) -> str | None:
    m = re.search(r"/(?:j|w|wc/join|s)/(\d{9,12})", url or "")
    return m.group(1) if m else None

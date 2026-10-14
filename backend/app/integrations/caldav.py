"""Minimal CalDAV client (read-only) for Yahoo, iCloud, Fastmail and other CalDAV calendars.

Sign in with an app-specific password (never the main account password). Discovers the person's calendars,
asks the server for events in a time window and returns them as iCalendar text for the normal parser.
"""
import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
import httpx
from app.integrations import ics_feed

class CalDavError(RuntimeError): pass

PRESETS = {
    "yahoo": {"label": "Yahoo Calendar", "url": "https://caldav.calendar.yahoo.com", "how": "Yahoo Account Security > Generate app password (choose 'Other app'). Use your full Yahoo email as the username and the app password below."},
    "icloud": {"label": "Apple iCloud Calendar", "url": "https://caldav.icloud.com", "how": "appleid.apple.com > Sign-In and Security > App-Specific Passwords. Username is your Apple ID email."},
    "fastmail": {"label": "Fastmail", "url": "https://caldav.fastmail.com", "how": "Fastmail Settings > Privacy & Security > App passwords (access: calendars). Username is your Fastmail address."},
    "other": {"label": "Other CalDAV calendar", "url": "", "how": "Enter the CalDAV server address your calendar provider gives you, with your username and an app password."},
}
NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
MAX_BYTES = 10 * 1024 * 1024

def _xml(text: str):
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper(): raise CalDavError("The calendar server sent something unexpected.")
    try: return ET.fromstring(text)
    except ET.ParseError: raise CalDavError("The calendar server's answer could not be read.")

class _Session:
    def __init__(self, user: str, password: str):
        self.c = httpx.AsyncClient(timeout=25, auth=(user, password), follow_redirects=False, headers={"User-Agent": "MeetingIntelligence/1.0"})
        self.total = 0
    async def close(self): await self.c.aclose()
    async def req(self, method: str, url: str, body: str, depth: str = "0", ctype: str = "application/xml; charset=utf-8") -> str:
        for _ in range(4):
            await asyncio.to_thread(ics_feed.validate, url)
            try: r = await self.c.request(method, url, content=body.encode(), headers={"Depth": depth, "Content-Type": ctype})
            except httpx.HTTPError as exc: raise CalDavError(f"Could not reach the calendar server ({type(exc).__name__}).")
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"): url = urljoin(url, r.headers["location"]); continue
            if r.status_code in (401, 403): raise CalDavError("The calendar server refused the sign-in. Use an app-specific password and the full username.")
            if r.status_code >= 400 and r.status_code != 207: raise CalDavError(f"The calendar server answered with an error ({r.status_code}).")
            self.total += len(r.content)
            if self.total > MAX_BYTES: raise CalDavError("The calendar is larger than 10 MB.")
            r.encoding = "utf-8"; return r.text, url
        raise CalDavError("The calendar server redirected too many times.")

def _hrefs(root, path: str) -> list[str]:
    return [h.text.strip() for h in root.findall(path, NS) if h.text]

async def discover(s: _Session, base: str) -> list[str]:
    """Returns calendar collection URLs."""
    body = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/><c:calendar-home-set xmlns:c="urn:ietf:params:xml:ns:caldav"/><d:resourcetype/></d:prop></d:propfind>'
    text, url = await s.req("PROPFIND", base, body, "0"); root = _xml(text)
    home = _hrefs(root, ".//c:calendar-home-set/d:href")
    if not home:
        princ = _hrefs(root, ".//d:current-user-principal/d:href")
        if princ:
            purl = urljoin(url, princ[0]); text, url = await s.req("PROPFIND", purl, body, "0"); root = _xml(text); home = _hrefs(root, ".//c:calendar-home-set/d:href")
    if not home:   # the address may already be the calendar (or a home folder) itself
        home = [url]; 
    hurl = urljoin(url, home[0])
    lst = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:resourcetype/><c:supported-calendar-component-set/></d:prop></d:propfind>'
    text, hurl2 = await s.req("PROPFIND", hurl, lst, "1"); root = _xml(text); cals = []
    for resp in root.findall("d:response", NS):
        if resp.find(".//d:resourcetype/c:calendar", NS) is None: continue
        comps = [c.get("name") for c in resp.findall(".//c:supported-calendar-component-set/c:comp", NS)]
        if comps and "VEVENT" not in comps: continue
        href = resp.findtext("d:href", default="", namespaces=NS).strip()
        if href: cals.append(urljoin(hurl2, href))
    return cals[:20]

async def fetch_text(url: str, username: str, password: str, start: datetime, end: datetime) -> str:
    s = _Session(username, password); out = []
    try:
        cals = await discover(s, ics_feed.normalize(url))
        if not cals: raise CalDavError("No calendars were found on that account.")
        fmt = lambda d: d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        body = (f'<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><c:calendar-data/></d:prop>'
                f'<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:time-range start="{fmt(start)}" end="{fmt(end)}"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
        for cal in cals:
            text, _ = await s.req("REPORT", cal, body, "1")
            for d in _xml(text).findall(".//c:calendar-data", NS):
                if d.text and "BEGIN:VEVENT" in d.text.upper(): out.append(d.text)
    finally:
        await s.close()
    return "\n".join(out) if out else "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"

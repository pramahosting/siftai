"""Calendars that publish a private .ics link: Google Calendar, Yahoo, Outlook.com / Microsoft 365, iCloud and others.

The link is fetched over https only, from public addresses only (so a pasted link cannot be used to reach
internal services), with a size limit and a short timeout.
"""
import asyncio, ipaddress, socket
from urllib.parse import urlsplit
import httpx
from app.core.config import settings

MAX_BYTES = 10 * 1024 * 1024

class FeedError(RuntimeError): pass

PROVIDERS = {
    "google": {"label": "Google Calendar / Gmail", "how": "Google Calendar > Settings > your calendar > Integrate calendar > copy 'Secret address in iCal format'."},
    "yahoo": {"label": "Yahoo Calendar", "how": "Yahoo Calendar > Settings (gear) > your calendar > Share / Export, then copy the iCal link (or upload the exported .ics file)."},
    "outlook": {"label": "Outlook.com / Microsoft 365", "how": "Outlook on the web > Settings > Calendar > Shared calendars > Publish a calendar > choose 'Can view all details' > Publish > copy the ICS link."},
    "icloud": {"label": "Apple iCloud", "how": "Calendar app > share icon next to the calendar > Public Calendar > copy the link."},
    "other": {"label": "Other calendar (.ics link)", "how": "Any calendar that gives you a link ending in .ics (webcal:// links work too)."},
}

def normalize(url: str) -> str:
    u = (url or "").strip()
    if u.lower().startswith("webcal://"): u = "https://" + u[9:]
    return u

def _public(host: str) -> bool:
    try: infos = socket.getaddrinfo(host, None)
    except socket.gaierror: raise FeedError("That address could not be found.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified: return False
    return True

def validate(url: str) -> str:
    u = normalize(url)
    parts = urlsplit(u)
    allow = settings.calendar_feed_allow_private
    if parts.scheme != "https" and not (allow and parts.scheme == "http"):
        raise FeedError("The calendar link must start with https:// (or webcal://).")
    if not parts.hostname: raise FeedError("That does not look like a web address.")
    if not allow and not _public(parts.hostname): raise FeedError("That address is not a public website, so it was refused.")
    return u

async def fetch_text(url: str) -> str:
    u = await asyncio.to_thread(validate, url)
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as c:
            async with c.stream("GET", u, headers={"Accept": "text/calendar, */*", "User-Agent": "MeetingIntelligence/1.0"}) as r:
                if 300 <= r.status_code < 400: raise FeedError("The calendar link redirected somewhere else, so it was not followed. Use the final link.")
                if r.status_code in (401, 403, 404): raise FeedError(f"The calendar link was refused ({r.status_code}). Check that it is the secret/published link.")
                if r.status_code >= 400: raise FeedError(f"The calendar service answered with an error ({r.status_code}).")
                data = b""
                async for chunk in r.aiter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES: raise FeedError("The calendar is larger than 10 MB.")
    except httpx.HTTPError as exc:
        raise FeedError(f"Could not reach the calendar ({type(exc).__name__}).")
    text = data.decode("utf-8-sig", errors="ignore")
    if "BEGIN:VCALENDAR" not in text.upper(): raise FeedError("That link did not return a calendar (.ics) file.")
    return text

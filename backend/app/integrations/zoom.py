"""Zoom (Server-to-Server OAuth): create meetings and fetch official cloud-recording transcripts.

Settings come from Admin settings > Zoom. Nothing is recorded or joined by this app; it only reads a transcript
Zoom has already produced and creates scheduled meetings through Zoom's own API.
"""
import time
from datetime import datetime, timezone
import httpx
from app.core.config import settings

API = "https://api.zoom.us/v2"
TOKEN_URL = "https://zoom.us/oauth/token"
_tok = {"v": None, "exp": 0.0, "k": None}

class ZoomUnavailable(RuntimeError): pass

def configured() -> bool:
    return bool(settings.zoom_account_id and settings.zoom_client_id and settings.zoom_client_secret)

async def _token() -> str:
    if not configured(): raise ZoomUnavailable("Zoom is not configured. An administrator can add it in Admin settings > Zoom.")
    key = (settings.zoom_account_id, settings.zoom_client_id)
    if _tok["v"] and _tok["k"] == key and time.time() < _tok["exp"] - 60: return _tok["v"]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(TOKEN_URL, params={"grant_type": "account_credentials", "account_id": settings.zoom_account_id}, auth=(settings.zoom_client_id, settings.zoom_client_secret))
    if r.status_code >= 400: raise ZoomUnavailable(f"Zoom sign-in failed ({r.status_code}). Check the account ID, client ID and secret.")
    j = r.json(); _tok.update(v=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)), k=key)
    return _tok["v"]

async def _req(method: str, path: str, **kw):
    token = await _token()
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.request(method, API + path if path.startswith("/") else path, headers={"Authorization": f"Bearer {token}"}, **kw)
    if r.status_code == 429: raise ZoomUnavailable("Zoom is throttling requests. Try again in a minute.")
    return r

async def ping() -> dict:
    r = await _req("GET", "/users/me")
    if r.status_code >= 400: raise ZoomUnavailable(f"Zoom answered {r.status_code}. Check the app's scopes.")
    j = r.json(); return {"email": j.get("email"), "account": j.get("account_id")}

async def create_meeting(topic: str, start: datetime, minutes: int, timezone_name: str, host: str = "me", agenda: str = "") -> dict:
    body = {"topic": topic[:200], "type": 2, "start_time": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "duration": max(5, int(minutes)),
            "timezone": timezone_name, "agenda": agenda[:2000], "settings": {"join_before_host": False, "waiting_room": True, "auto_recording": "none"}}
    r = await _req("POST", f"/users/{host}/meetings", json=body)
    if r.status_code >= 400: raise ZoomUnavailable(f"Zoom could not create the meeting ({r.status_code}). The app needs the meeting:write scope.")
    j = r.json(); return {"id": str(j["id"]), "join_url": j["join_url"], "start_url": j.get("start_url"), "password": j.get("password")}

async def transcript_for_meeting(meeting_id: str) -> tuple[str, str]:
    """Returns (recording reference, WebVTT text) of the newest cloud-recording transcript, or raises ZoomUnavailable."""
    r = await _req("GET", f"/meetings/{meeting_id}/recordings")
    if r.status_code == 404: raise ZoomUnavailable("Zoom has no cloud recording for this meeting yet. Cloud recording with 'Audio transcript' must be on in Zoom.")
    if r.status_code >= 400: raise ZoomUnavailable(f"Zoom answered {r.status_code} when looking for the recording. The app needs the cloud_recording:read scope.")
    files = [f for f in r.json().get("recording_files", []) if (f.get("file_type") or "").upper() in ("TRANSCRIPT",) or (f.get("recording_type") or "") == "audio_transcript"]
    if not files: raise ZoomUnavailable("The Zoom recording has no transcript yet. Turn on 'Audio transcript' in Zoom's cloud recording settings; it appears a few minutes after the meeting ends.")
    f = sorted(files, key=lambda x: x.get("recording_end", ""))[-1]
    d = await _req("GET", f["download_url"], follow_redirects=True)
    if d.status_code >= 400: raise ZoomUnavailable(f"The transcript could not be downloaded ({d.status_code}).")
    return str(f.get("id") or meeting_id), d.text

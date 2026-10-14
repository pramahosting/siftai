"""Built-in video meeting rooms.

Browsers connect directly to each other (WebRTC); this server only introduces them (signalling over a WebSocket),
hands out the STUN/TURN settings and stores recordings the host chooses to make. The room code in the link is the
secret, so guests can join without an account. Suited to small meetings (about 8 people).
"""
import asyncio, hmac, json, logging, os, secrets, shutil, time, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import APIRouter, Header, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.core.security import principal
from app.core import runtime_settings as rs
from app.models import User, Meeting, Room, RoomRecording, Job, AuditLog

log = logging.getLogger("meeting_platform")
router = APIRouter(prefix="/api/v1")
MAX_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
WEBM = bytes.fromhex("1A45DFA3")

def ice_config() -> list[dict]:
    urls = [u.strip() for u in (settings.ice_servers or "").split(",") if u.strip()]
    out = []
    for u in urls:
        e = {"urls": u}
        if u.lower().startswith(("turn:", "turns:")) and settings.turn_username: e.update(username=settings.turn_username, credential=settings.turn_credential)
        out.append(e)
    return out

def room_url(base_url: str, code: str) -> str:
    p = urlsplit(base_url or "")
    if p.scheme not in ("http", "https") or not p.netloc: raise HTTPException(422, "Could not work out this app's web address.")
    return f"{p.scheme}://{p.netloc}/#/room/{code}"

ACCESS = ("open", "passcode", "signed_in")

def clean_access(value, passcode=None) -> tuple[str, str | None]:
    """Return (access, passcode) with defaults from Admin settings. A passcode is made when one is needed."""
    access = str(value or "").strip().lower()
    if access not in ACCESS: access = settings.room_default_access if settings.room_default_access in ACCESS else "open"
    if access != "passcode": return access, None
    pc = "".join(ch for ch in str(passcode or "") if ch.isalnum())[:12]
    if len(pc) < 4: pc = f"{secrets.randbelow(10**6):06d}"
    return access, pc

async def make_room(db: AsyncSession, user: User, title: str, base_url: str, meeting: Meeting | None = None, start: datetime | None = None, minutes: int = 60,
                    access: str | None = None, passcode: str | None = None, waiting_room: bool | None = None) -> tuple[Room, Meeting]:
    await rs.apply_overrides(db)
    access, passcode = clean_access(access, passcode)
    waiting = settings.room_default_waiting if waiting_room is None else bool(waiting_room)
    code = secrets.token_urlsafe(9).replace("_", "x").replace("-", "y")
    url = room_url(base_url, code)
    if meeting is None:
        start = start or datetime.now(timezone.utc)
        meeting = Meeting(owner_id=user.id, external_id=f"room:{code}", title=title, organizer=user.email, start_at=start, end_at=start + timedelta(minutes=minutes), sensitivity="normal", join_url=url, status="scheduled")
        db.add(meeting); await db.flush()
    else: meeting.join_url = url
    room = Room(code=code, host_id=user.id, meeting_id=meeting.id, title=title[:200], access=access, passcode=passcode, waiting_room=waiting, allow_guests=access != "signed_in")
    db.add(room); await db.commit()
    return room, meeting

@router.post("/rooms")
async def create_room(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Start an instant meeting room now."""
    title = (str(payload.get("title") or "").strip() or f"{user.display_name or user.email}'s meeting")[:200]
    room, meeting = await make_room(db, user, title, str(payload.get("base_url") or ""), access=payload.get("access"), passcode=payload.get("passcode"), waiting_room=payload.get("waiting_room"))
    db.add(AuditLog(actor=user.email, action="room.create", resource_type="room", safe_metadata={"access": room.access, "waiting_room": room.waiting_room})); await db.commit()
    return {"code": room.code, "meeting_id": meeting.id, "url": meeting.join_url, "access": room.access, "passcode": room.passcode, "waiting_room": room.waiting_room}

@router.get("/rooms/{code}")
async def room_info(code: str, authorization: str | None = Header(None), db: AsyncSession = Depends(get_db)):
    room = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
    if not room: raise HTTPException(404, "This meeting link is not valid.")
    host = await db.get(User, room.host_id)
    me = await _user_from_token(authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else None)
    return {"access": room.access, "waiting_room": room.waiting_room, "you_are_host": bool(me and me.id == room.host_id), "signed_in": bool(me), "title": room.title, "ended": room.ended_at is not None, "host": (host.display_name or host.email) if host else "", "ice": ice_config(),
            "max_people": settings.room_max_people, "allow_guests": room.allow_guests, "people_now": len(HUB.get(code, {}).get("peers", {}))}

@router.get("/rooms/{code}/host")
async def room_host_view(code: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    room = await _host_room_any(db, code, user)
    return {"access": room.access, "passcode": room.passcode, "waiting_room": room.waiting_room, "url": (await db.get(Meeting, room.meeting_id)).join_url if room.meeting_id else None}

@router.patch("/rooms/{code}")
async def room_change(code: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """The host changes who can join. Applies to people who join from now on."""
    room = await _host_room_any(db, code, user)
    if "access" in payload or "passcode" in payload:
        room.access, room.passcode = clean_access(payload.get("access", room.access), payload.get("passcode") or (room.passcode if payload.get("access", room.access) == "passcode" else None))
        room.allow_guests = room.access != "signed_in"
    if "waiting_room" in payload: room.waiting_room = bool(payload["waiting_room"])
    await db.commit()
    return {"access": room.access, "passcode": room.passcode, "waiting_room": room.waiting_room}

async def _host_room_any(db: AsyncSession, code: str, user: User) -> Room:
    room = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
    if not room: raise HTTPException(404, "Meeting not found")
    if room.host_id != user.id: raise HTTPException(403, "Only the host can do this.")
    return room

async def _user_from_token(token: str | None) -> User | None:
    if not token: return None
    async with SessionLocal() as db:
        try: return await principal(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), db)
        except HTTPException: return None

# ---- signalling hub (one server process; rooms are small) ----
HUB: dict[str, dict] = {}

async def _send(ws: WebSocket, msg: dict):
    try: await ws.send_text(json.dumps(msg))
    except Exception: pass

async def _broadcast(code: str, msg: dict, skip: str | None = None):
    for pid, p in list(HUB.get(code, {}).get("peers", {}).items()):
        if pid != skip: await _send(p["ws"], msg)

_FAILS: dict[str, list[float]] = {}      # wrong passcode attempts per room

def _passcode_ok(code: str, given: str, real: str | None) -> tuple[bool, str]:
    now = time.time(); tries = [t for t in _FAILS.get(code, []) if now - t < 600]
    if len(tries) >= 10: _FAILS[code] = tries; return False, "Too many wrong passcodes. Wait a few minutes and try again."
    if real and hmac.compare_digest(str(given or "").strip().encode(), real.encode()): return True, ""
    tries.append(now); _FAILS[code] = tries
    return False, "That passcode is not right."

async def _tell_hosts(state: dict):
    waiting = [{"id": i, "name": w["name"]} for i, w in state["waiting"].items()]
    for p in list(state["peers"].values()):
        if p["host"]: await _send(p["ws"], {"type": "waiting-list", "list": waiting})

async def _admit(code: str, state: dict, pid: str, ws: WebSocket, name: str, is_host: bool) -> bool:
    if len(state["peers"]) >= max(2, settings.room_max_people):
        await _send(ws, {"type": "error", "message": "This meeting is full."}); return False
    peers_before = [{"id": i, "name": p["name"], "host": p["host"]} for i, p in state["peers"].items()]
    state["peers"][pid] = {"ws": ws, "name": name, "host": is_host}
    await _send(ws, {"type": "welcome", "id": pid, "host": is_host, "peers": peers_before, "recording": state["recording"],
                     "waiting": [{"id": i, "name": w["name"]} for i, w in state["waiting"].items()] if is_host else []})
    await _broadcast(code, {"type": "peer-joined", "id": pid, "name": name, "host": is_host}, skip=pid)
    return True

@router.websocket("/ws/rooms/{code}")
async def room_socket(ws: WebSocket, code: str):
    await ws.accept()
    pid = None
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=20))
        if first.get("type") != "join": await ws.close(); return
        async with SessionLocal() as db:
            room = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
            if room: host_id, ended, access, passcode, waiting_room = room.host_id, room.ended_at is not None, room.access, room.passcode, room.waiting_room
        if not room or ended:
            await _send(ws, {"type": "error", "message": "This meeting has ended or the link is not valid."}); await ws.close(); return
        user = await _user_from_token(first.get("token"))
        is_host = bool(user and user.id == host_id)
        if access == "signed_in" and not user:
            await _send(ws, {"type": "error", "code": "signin", "message": "Sign in to join this meeting. It is only open to people with an account."}); await ws.close(); return
        if access == "passcode" and not is_host:
            ok, why = _passcode_ok(code, first.get("passcode"), passcode)
            if not ok: await _send(ws, {"type": "error", "code": "passcode", "message": why}); await ws.close(); return
        name = (str(first.get("name") or "").strip() or (user.display_name if user else "") or "Guest")[:60]
        state = HUB.setdefault(code, {"peers": {}, "waiting": {}, "recording": False})
        pid = uuid.uuid4().hex[:10]
        if waiting_room and not is_host:
            state["waiting"][pid] = {"ws": ws, "name": name}
            await _send(ws, {"type": "waiting"}); await _tell_hosts(state)
        elif not await _admit(code, state, pid, ws, name, is_host):
            pid = None; await ws.close(); return
        while True:
            msg = json.loads(await ws.receive_text()); t = msg.get("type")
            if pid not in state["peers"]:
                continue                                  # still in the waiting room: nothing else is allowed yet
            if t == "signal":
                target = state["peers"].get(msg.get("to"))
                if target: await _send(target["ws"], {"type": "signal", "from": pid, "data": msg.get("data")})
            elif t == "chat":
                text = str(msg.get("text") or "")[:2000]
                if text.strip(): await _broadcast(code, {"type": "chat", "from": pid, "name": name, "text": text, "at": datetime.now(timezone.utc).isoformat()})
            elif t == "state":      # mic / camera / screen-share indicators
                await _broadcast(code, {"type": "state", "id": pid, "mic": bool(msg.get("mic")), "cam": bool(msg.get("cam")), "screen": bool(msg.get("screen"))}, skip=pid)
            elif is_host and t in ("admit", "admit_all"):
                ids = list(state["waiting"]) if t == "admit_all" else [msg.get("id")]
                for wid in ids:
                    w = state["waiting"].pop(wid, None)
                    if w and not await _admit(code, state, wid, w["ws"], w["name"], False):
                        try: await w["ws"].close()
                        except Exception: pass
                await _tell_hosts(state)
            elif is_host and t == "deny":
                w = state["waiting"].pop(msg.get("id"), None)
                if w:
                    await _send(w["ws"], {"type": "denied"})
                    try: await w["ws"].close()
                    except Exception: pass
                await _tell_hosts(state)
            elif is_host and t == "record":
                state["recording"] = bool(msg.get("on")); await _broadcast(code, {"type": "recording", "on": state["recording"]})
            elif is_host and t == "kick":
                target = state["peers"].get(msg.get("id"))
                if target and msg.get("id") != pid: await _send(target["ws"], {"type": "kicked"}); await target["ws"].close()
            elif is_host and t == "end":
                async with SessionLocal() as db:
                    r = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
                    if r: r.ended_at = datetime.now(timezone.utc); await db.commit()
                await _broadcast(code, {"type": "ended"})
                for p in list(state["peers"].values()) + list(state["waiting"].values()):
                    try: await p["ws"].close()
                    except Exception: pass
                break
    except (WebSocketDisconnect, asyncio.TimeoutError, json.JSONDecodeError, RuntimeError):
        pass
    finally:
        state = HUB.get(code)
        if state and pid:
            if state["waiting"].pop(pid, None) is not None: await _tell_hosts(state)
            if pid in state["peers"]:
                state["peers"].pop(pid, None)
                await _broadcast(code, {"type": "peer-left", "id": pid})
            if not state["peers"] and not state["waiting"]: HUB.pop(code, None)

# ---- recordings ----
async def _host_room(db: AsyncSession, code: str, user: User) -> Room:
    room = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
    if not room: raise HTTPException(404, "Meeting not found")
    if room.host_id != user.id: raise HTTPException(403, "Only the host can save a recording.")
    return room

async def _save_upload(f: UploadFile, dest: Path, limit: int) -> int:
    size, head = 0, b""
    try:
        with dest.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > limit: raise HTTPException(413, "The recording is larger than the allowed size.")
                if not head: head = chunk[:4]
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True); raise
    if head != WEBM: dest.unlink(missing_ok=True); raise HTTPException(415, "The recording is not a valid WebM file.")
    return size

@router.post("/rooms/{code}/recording")
async def save_recording(code: str, consent_acknowledged: bool = Form(...), audio: UploadFile = File(...), video: UploadFile | None = File(None),
                         user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    if not consent_acknowledged: raise HTTPException(400, "Confirm that participants were told the meeting was recorded.")
    room = await _host_room(db, code, user)
    base = Path(settings.audio_storage_dir) / "recordings"; base.mkdir(parents=True, exist_ok=True)
    rid = str(uuid.uuid4()); keep = base / f"{rid}.webm"
    audio_path = Path(settings.audio_storage_dir) / f"{rid}-speech.webm"; Path(settings.audio_storage_dir).mkdir(parents=True, exist_ok=True)
    a_size = await _save_upload(audio, audio_path, settings.audio_max_bytes)
    size = a_size
    if video is not None and video.filename:
        size = await _save_upload(video, keep, MAX_VIDEO_BYTES)
        has_video = True
    else:
        shutil.copyfile(audio_path, keep); has_video = False          # audio-only meeting: keep a copy for download
    db.add(RoomRecording(id=rid, room_id=room.id, path=str(keep), size_bytes=size, has_video=has_video))
    note = "Recording saved."
    meeting = await db.get(Meeting, room.meeting_id) if room.meeting_id else None
    from app.services.llm import transcription_configured
    if meeting and transcription_configured():
        db.add(Job(kind="transcribe_audio", payload={"meeting_id": meeting.id, "path": str(audio_path), "filename": f"{rid}.webm", "owner_id": user.id}))
        meeting.transcript_status = "queued"; note = "Recording saved. The transcript is being prepared and will appear under Transcripts."
    else:
        audio_path.unlink(missing_ok=True)
        note = "Recording saved. To get a transcript, an administrator must add a transcription model in Admin settings, then upload the audio on the Meetings page."
    db.add(AuditLog(actor=user.email, action="room.recording.saved", resource_type="room", safe_metadata={"bytes": size, "video": has_video}))
    await db.commit()
    return {"id": rid, "message": note}

@router.get("/recordings")
async def my_recordings(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(RoomRecording, Room).join(Room, Room.id == RoomRecording.room_id).where(Room.host_id == user.id).order_by(RoomRecording.created_at.desc()).limit(100))).all()
    return [{"id": r.id, "title": room.title, "created_at": r.created_at.isoformat(), "size_bytes": r.size_bytes, "has_video": r.has_video} for r, room in rows]

@router.get("/recordings/{rid}/file")
async def recording_file(rid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(RoomRecording, Room).join(Room, Room.id == RoomRecording.room_id).where(RoomRecording.id == rid))).first()
    if not row or row[1].host_id != user.id: raise HTTPException(404, "Recording not found")
    if not os.path.exists(row[0].path): raise HTTPException(410, "The recording file is no longer on this computer.")
    return FileResponse(row[0].path, media_type="video/webm" if row[0].has_video else "audio/webm", filename=f"{row[1].title[:40] or 'meeting'}.webm")

@router.delete("/recordings/{rid}")
async def delete_recording(rid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(RoomRecording, Room).join(Room, Room.id == RoomRecording.room_id).where(RoomRecording.id == rid))).first()
    if not row or row[1].host_id != user.id: raise HTTPException(404, "Recording not found")
    Path(row[0].path).unlink(missing_ok=True); await db.delete(row[0])
    db.add(AuditLog(actor=user.email, action="room.recording.deleted", resource_type="room", safe_metadata={})); await db.commit()
    return {"ok": True}

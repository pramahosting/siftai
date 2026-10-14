"""Automatic calendar sync: keeps today's meetings (and the next 7 days) current.

Runs from the background worker on a schedule and whenever the local date changes.
Only eligible events are stored (private, cancelled and all-day events are excluded
before processing, same as briefings). Existing meetings are updated when the
calendar changes, and meetings removed or cancelled in the calendar are marked cancelled.
"""
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.integrations.graph import graph, GraphUnavailable, mailbox_for
from app.integrations import machine_calendar as machine
from app.integrations.machine_calendar import MachineCalendarError
from app.models import Meeting, IntegrationSetting, User
from app.services.policy import eligible
from app.services.briefings import graph_datetime

log = logging.getLogger("meeting_platform")
STATUS_KEY = "calendar_sync"
DAYS_AHEAD = 7

def status_key(user_id: str) -> str:
    return f"{STATUS_KEY}:{user_id}"

def consent_key(user_id: str) -> str:
    return f"machine_calendar:{user_id}"

def graph_configured() -> bool:
    return bool(settings.entra_tenant_id and settings.graph_client_id and settings.graph_client_secret)

async def get_consent(db: AsyncSession, user_id: str) -> str | None:
    row = await db.get(IntegrationSetting, consent_key(user_id))
    return (row.value or {}).get("consent") if row else None

async def set_consent(db: AsyncSession, user_id: str, allow: bool) -> None:
    row = await db.get(IntegrationSetting, consent_key(user_id)); val = {"consent": "allowed" if allow else "denied", "at": datetime.now(timezone.utc).isoformat()}
    if row: row.value = val
    else: db.add(IntegrationSetting(key=consent_key(user_id), value=val))
    await db.commit()

def feeds_key(user_id: str) -> str:
    return f"calendar_feeds:{user_id}"

async def get_feeds(db: AsyncSession, user_id: str) -> list[dict]:
    row = await db.get(IntegrationSetting, feeds_key(user_id))
    return list((row.value or {}).get("items", [])) if row else []

async def save_feeds(db: AsyncSession, user_id: str, items: list[dict]) -> None:
    row = await db.get(IntegrationSetting, feeds_key(user_id)); val = {"items": items}
    if row: row.value = val
    else: db.add(IntegrationSetting(key=feeds_key(user_id), value=val))
    await db.commit()

def caldav_error():
    from app.integrations.caldav import CalDavError
    return CalDavError

async def feed_events(db: AsyncSession, user_id: str, start: datetime, end: datetime) -> tuple[list[dict], list[str]]:
    """Events from every calendar link the person added. A broken link is reported, never fatal."""
    from app.integrations import ics_feed
    from app.core import runtime_settings as rs
    out, errors, items = [], [], await get_feeds(db, user_id)
    for it in items:
        try:
            if it.get("kind") == "caldav":
                from app.integrations import caldav
                text = await caldav.fetch_text(rs._dec(it["url"]), rs._dec(it["username"]), rs._dec(it["password"]), start, end)
            else:
                text = await ics_feed.fetch_text(rs._dec(it["url"]))
            out += machine.events_from_ics_text(text, start, end); it["ok"] = True; it["error"] = None
        except (ics_feed.FeedError, caldav_error()) as exc:
            it["ok"] = False; it["error"] = str(exc); errors.append(f"{it.get('label') or it.get('provider')}: {exc}")
        it["at"] = datetime.now(timezone.utc).isoformat()
    if items: await save_feeds(db, user_id, items)
    mail = await get_mail(db, user_id)
    if mail and mail.get("import_invites"):
        from app.integrations import mail as mailer
        try:
            out += machine.events_from_ics_text(await mailer.find_invites(mail), start, end)
            mail["ok"] = True; mail["error"] = None
        except mailer.MailError as exc:
            mail["ok"] = False; mail["error"] = str(exc); errors.append(f"Inbox invitations: {exc}")
        mail["at"] = datetime.now(timezone.utc).isoformat()
        stored = dict(mail); from app.core import runtime_settings as rs; stored["password"] = rs._enc(mail["password"]) if not str(mail["password"]).startswith("enc:") else mail["password"]
        await save_mail(db, user_id, stored)
    return out, errors

def mail_key(user_id: str) -> str:
    return f"mail_account:{user_id}"

async def get_mail(db: AsyncSession, user_id: str) -> dict | None:
    """The person's saved mailbox with the password decrypted (never returned to the browser)."""
    from app.core import runtime_settings as rs
    row = await db.get(IntegrationSetting, mail_key(user_id))
    if not row or not row.value: return None
    v = dict(row.value); v["password"] = rs._dec(v.get("password", "")); return v

async def save_mail(db: AsyncSession, user_id: str, value: dict | None) -> None:
    row = await db.get(IntegrationSetting, mail_key(user_id))
    if value is None:
        if row: await db.delete(row)
    elif row: row.value = value
    else: db.add(IntegrationSetting(key=mail_key(user_id), value=value))
    await db.commit()

def upload_key(user_id: str) -> str:
    return f"calendar_ics:{user_id}"

async def get_upload(db: AsyncSession, user_id: str) -> str | None:
    row = await db.get(IntegrationSetting, upload_key(user_id))
    return (row.value or {}).get("text") if row else None

async def save_upload(db: AsyncSession, user_id: str, text: str, name: str) -> None:
    val = {"text": text, "name": name[:200], "at": datetime.now(timezone.utc).isoformat()}
    row = await db.get(IntegrationSetting, upload_key(user_id))
    if row: row.value = val
    else: db.add(IntegrationSetting(key=upload_key(user_id), value=val))
    await db.commit()

async def machine_usable(db: AsyncSession, user_id: str) -> bool:
    return bool(settings.machine_calendar_allowed and await get_consent(db, user_id) == "allowed" and machine.detect()["available"])

async def machine_status(db: AsyncSession, user_id: str, local_request: bool) -> dict:
    info = machine.detect()
    return {"allowed_by_admin": bool(settings.machine_calendar_allowed), "available": info["available"], "source": info["source"], "consent": await get_consent(db, user_id),
            "can_grant": bool(local_request), "in_use": await machine_usable(db, user_id), "note": info.get("note"), "outlook_accounts": machine._LAST.get("accounts", []), "uploaded": bool(await get_upload(db, user_id)),
            "folders": [str(p) for p in machine.ics_folders()][:8]}

def as_utc(v: datetime) -> datetime:
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)

async def user_timezone(db: AsyncSession) -> ZoneInfo:
    prefs = await db.get(IntegrationSetting, "preferences")
    name = (prefs.value.get("timezone") if prefs and prefs.value else None) or settings.default_timezone
    try: return ZoneInfo(name)
    except Exception: return ZoneInfo(settings.default_timezone)

def today_window(tz: ZoneInfo) -> tuple[datetime, datetime]:
    now = datetime.now(tz)
    start = datetime.combine(now.date(), time.min, tzinfo=tz)
    return start, start + timedelta(days=1)

async def _save_status(db: AsyncSession, user_id: str, **values) -> None:
    key = status_key(user_id)
    row = await db.get(IntegrationSetting, key)
    data = dict(row.value) if row and row.value else {}
    data.update(values)
    if row: row.value = data
    else: db.add(IntegrationSetting(key=key, value=data))
    await db.commit()

async def sync_calendar(db: AsyncSession, user_id: str, mailbox: str | None = None) -> dict:
    """Pull today + next days from Microsoft Graph and upsert eligible meetings for one user."""
    if mailbox is None:
        u = await db.get(User, user_id); mailbox = mailbox_for(u.email) if u else None
    tz = await user_timezone(db)
    start, _ = today_window(tz)
    end = start + timedelta(days=DAYS_AHEAD + 1)
    source, raw, graph_err = "graph", None, None
    if graph_configured() and mailbox:
        try: raw = await graph.calendar(start, end, mailbox)
        except GraphUnavailable as exc: graph_err = exc
    if raw is None:
        parts, used = [], []
        feed_raw, feed_errors = await feed_events(db, user_id, start, end)
        _m = await get_mail(db, user_id)
        if (await get_feeds(db, user_id) or (_m and _m.get("import_invites"))) and not feed_errors: used.append("link")
        parts += feed_raw
        if feed_raw and "link" not in used: used.append("link")
        uploaded = await get_upload(db, user_id)
        if uploaded:
            parts += machine.events_from_ics_text(uploaded, start, end); used.append("upload")
        if await machine_usable(db, user_id):
            try: parts += await machine.fetch(start, end); used.append("machine")
            except MachineCalendarError as exc:
                if not used: raise GraphUnavailable(str(exc))
        if used:
            seen_ids, raw = set(), []
            for e in parts:
                if e["id"] not in seen_ids: seen_ids.add(e["id"]); raw.append(e)
            source = "machine" if "machine" in used else ("link" if "link" in used else "upload")
        elif feed_errors: raise GraphUnavailable("; ".join(feed_errors)[:300])
        elif graph_err: raise graph_err
        else: raise GraphUnavailable("No calendar is connected. Add a calendar link (Google, Yahoo, Outlook.com, iCloud) or upload a calendar (.ics) file under Connections, allow the calendar on this computer, or connect Microsoft 365 in Admin settings.")
    selected = [e for e in raw if eligible(e)]
    seen: set[str] = set(); added = updated = 0
    for e in selected:
        ext = e["id"]; seen.add(ext)
        start_at = graph_datetime(e["start"]["dateTime"]); end_at = graph_datetime(e["end"]["dateTime"])
        title = e.get("subject") or "Meeting"
        organizer = ((e.get("organizer") or {}).get("emailAddress") or {}).get("address", "")
        row = (await db.execute(select(Meeting).where(Meeting.owner_id == user_id, Meeting.external_id == ext))).scalar_one_or_none()
        if not row:
            db.add(Meeting(owner_id=user_id, external_id=ext, title=title, organizer=organizer, start_at=start_at, end_at=end_at,
                           sensitivity=e.get("sensitivity", "normal"), join_url=e.get("onlineMeetingUrl"), status="scheduled")); added += 1
        else:
            changed = (row.title != title or as_utc(row.start_at) != as_utc(start_at) or as_utc(row.end_at) != as_utc(end_at) or row.organizer != organizer or row.status == "cancelled")
            if changed:
                row.title, row.start_at, row.end_at, row.organizer = title, start_at, end_at, organizer
                if row.status == "cancelled": row.status = "scheduled"
                updated += 1
    # Meetings that disappeared from the calendar window (cancelled/declined/made private) are marked cancelled.
    stale = (await db.execute(select(Meeting).where(
        Meeting.owner_id == user_id, Meeting.status == "scheduled", ~Meeting.external_id.like("demo-%"), ~Meeting.external_id.like("zoom:%"), ~Meeting.external_id.like("local:%"), ~Meeting.external_id.like("room:%"),
        Meeting.start_at >= start.astimezone(timezone.utc), Meeting.start_at < end.astimezone(timezone.utc)))).scalars().all()
    cancelled = 0
    for m in stale:
        if m.external_id not in seen: m.status = "cancelled"; cancelled += 1
    await db.commit()
    result = {"added": added, "updated": updated, "cancelled": cancelled, "eligible": len(selected), "source": source}
    await _save_status(db, user_id, at=datetime.now(timezone.utc).isoformat(), ok=True, error=None, **result)
    return result

async def sync_one_safely(user_id: str) -> dict | None:
    """Sync one person in their own session so one failure never affects anyone else."""
    from app.core.db import SessionLocal
    async with SessionLocal() as db:
        try:
            return await sync_calendar(db, user_id)
        except GraphUnavailable as exc:
            await db.rollback()
            await _save_status(db, user_id, at=datetime.now(timezone.utc).isoformat(), ok=False, error=str(exc)[:200])
        except Exception:
            await db.rollback(); log.exception("Automatic calendar sync failed")
            await _save_status(db, user_id, at=datetime.now(timezone.utc).isoformat(), ok=False, error="Calendar sync failed unexpectedly")
    return None

async def auto_sync(db: AsyncSession, concurrency: int = 4) -> dict:
    """Worker entry point: refresh calendars, a few people at a time. Uses Microsoft 365 when configured, otherwise this computer's calendar for people who allowed it."""
    import asyncio
    ids: set[str] = set()
    if graph_configured():
        ids |= {r[0] for r in (await db.execute(select(User.id).order_by(User.email).limit(2000))).all()}
    elif settings.machine_calendar_allowed and machine.detect()["available"]:
        keys = [r[0] for r in (await db.execute(select(IntegrationSetting.key).where(IntegrationSetting.key.like("machine_calendar:%")))).all()]
        ids |= {i for i in (k.split(":", 1)[1] for k in keys) if await get_consent(db, i) == "allowed"}
    # people with their own calendar links (Google, Yahoo, Outlook.com, iCloud) are refreshed too
    for r in (await db.execute(select(IntegrationSetting.key).where(IntegrationSetting.key.like("calendar_feeds:%")))).all(): ids.add(r[0].split(":", 1)[1])
    for r in (await db.execute(select(IntegrationSetting).where(IntegrationSetting.key.like("mail_account:%")))).scalars().all():
        if (r.value or {}).get("import_invites"): ids.add(r.key.split(":", 1)[1])
    ids = sorted(ids)
    if not ids: return {"users": 0}
    sem = asyncio.Semaphore(concurrency)
    async def run(uid):
        async with sem: return await sync_one_safely(uid)
    results = await asyncio.gather(*(run(u) for u in ids))
    return {"users": len(ids), "synced": sum(1 for r in results if r is not None)}

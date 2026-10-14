"""Connections: calendar links (Google, Yahoo, Outlook.com, iCloud), Zoom, and creating meetings."""
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal, require_admin
from app.core import runtime_settings as rs
from app.models import User, Meeting, AuditLog
from app.services import calendar_sync as cal
from app.integrations import ics_feed, zoom, caldav, mail as mailer
from app.integrations.graph import GraphUnavailable

router = APIRouter(prefix="/api/v1")

def _public_feed(it: dict) -> dict:
    host = ""
    try: host = urlsplit(rs._dec(it["url"])).hostname or ""
    except Exception: pass
    return {"id": it["id"], "provider": it["provider"], "kind": it.get("kind", "ics"), "label": it.get("label") or (caldav.PRESETS if it.get("kind") == "caldav" else ics_feed.PROVIDERS).get(it["provider"], {}).get("label", "Calendar"),
            "host": host, "ok": it.get("ok"), "error": it.get("error"), "at": it.get("at")}

async def _mail_public(db, user):
    m = await cal.get_mail(db, user.id)
    if not m: return None
    return {"provider": m.get("provider"), "address": m.get("address"), "import_invites": bool(m.get("import_invites")), "ok": m.get("ok"), "error": m.get("error"), "at": m.get("at")}

@router.get("/connections")
async def connections(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    return {"providers": [{"id": k, **v} for k, v in ics_feed.PROVIDERS.items()],
            "caldav_presets": [{"id": k, **v} for k, v in caldav.PRESETS.items()],
            "links": [_public_feed(i) for i in await cal.get_feeds(db, user.id)],
            "uploaded": bool(await cal.get_upload(db, user.id)),
            "computer": await cal.machine_status(db, user.id, True),
            "mail_presets": [{"id": k, "label": v["label"], "how": v["how"], "smtp_host": v["smtp"][0], "smtp_port": v["smtp"][1], "imap_host": v["imap"][0], "imap_port": v["imap"][1]} for k, v in mailer.PRESETS.items()],
            "mail": await _mail_public(db, user),
            "zoom": {"configured": zoom.configured()},
            "microsoft": {"configured": cal.graph_configured()}}

@router.post("/connections/calendar-links")
async def add_link(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    provider = payload.get("provider") if payload.get("provider") in ics_feed.PROVIDERS else "other"
    url = str(payload.get("url") or "").strip()
    if not url: raise HTTPException(422, "Paste the calendar link first.")
    items = await cal.get_feeds(db, user.id)
    if len(items) >= 10: raise HTTPException(422, "You can add up to 10 calendar links. Remove one first.")
    try: text = await ics_feed.fetch_text(url)          # test it before saving
    except ics_feed.FeedError as exc: raise HTTPException(422, str(exc))
    tz = await cal.user_timezone(db); start, _ = cal.today_window(tz)
    n = len(cal.machine.events_from_ics_text(text, start, start + timedelta(days=cal.DAYS_AHEAD + 1)))
    items.append({"id": uuid.uuid4().hex[:12], "provider": provider, "label": str(payload.get("label") or "")[:80], "url": rs._enc(ics_feed.normalize(url)), "ok": True, "error": None, "at": datetime.now(timezone.utc).isoformat()})
    await cal.save_feeds(db, user.id, items)
    db.add(AuditLog(actor=user.email, action="calendar.link.add", resource_type="calendar", safe_metadata={"provider": provider})); await db.commit()
    try: result = await cal.sync_calendar(db, user.id)
    except GraphUnavailable as exc: raise HTTPException(502, str(exc))
    return {"message": f"Calendar connected: {n} event(s) in the next {cal.DAYS_AHEAD} days, {result['added']} new meeting(s) added.", "links": [_public_feed(i) for i in await cal.get_feeds(db, user.id)]}

@router.post("/connections/caldav")
async def add_caldav(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    preset = payload.get("provider") if payload.get("provider") in caldav.PRESETS else "other"
    url = str(payload.get("url") or caldav.PRESETS[preset]["url"]).strip()
    username = str(payload.get("username") or "").strip(); password = str(payload.get("password") or "")
    if not url or not username or not password: raise HTTPException(422, "Enter the server address, username and app password.")
    items = await cal.get_feeds(db, user.id)
    if len(items) >= 10: raise HTTPException(422, "You can add up to 10 calendars. Remove one first.")
    tz = await cal.user_timezone(db); start, _ = cal.today_window(tz); end = start + timedelta(days=cal.DAYS_AHEAD + 1)
    try:
        text = await caldav.fetch_text(url, username, password, start, end)     # test before saving
    except (caldav.CalDavError, ics_feed.FeedError) as exc: raise HTTPException(422, str(exc))
    n = len(cal.machine.events_from_ics_text(text, start, end))
    items.append({"id": uuid.uuid4().hex[:12], "kind": "caldav", "provider": preset, "label": str(payload.get("label") or "")[:80], "url": rs._enc(url), "username": rs._enc(username),
                  "password": rs._enc(password), "ok": True, "error": None, "at": datetime.now(timezone.utc).isoformat()})
    await cal.save_feeds(db, user.id, items)
    db.add(AuditLog(actor=user.email, action="calendar.caldav.add", resource_type="calendar", safe_metadata={"provider": preset})); await db.commit()
    try: result = await cal.sync_calendar(db, user.id)
    except GraphUnavailable as exc: raise HTTPException(502, str(exc))
    return {"message": f"Calendar connected: {n} event(s) in the next {cal.DAYS_AHEAD} days, {result['added']} new meeting(s) added.", "links": [_public_feed(i) for i in await cal.get_feeds(db, user.id)]}

@router.delete("/connections/calendar-links/{link_id}")
async def remove_link(link_id: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    items = await cal.get_feeds(db, user.id)
    keep = [i for i in items if i["id"] != link_id]
    if len(keep) == len(items): raise HTTPException(404, "Calendar link not found")
    await cal.save_feeds(db, user.id, keep)
    db.add(AuditLog(actor=user.email, action="calendar.link.remove", resource_type="calendar", safe_metadata={})); await db.commit()
    return {"links": [_public_feed(i) for i in keep]}

@router.post("/connections/sync")
async def sync_now(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    try: result = await cal.sync_calendar(db, user.id)
    except GraphUnavailable as exc: raise HTTPException(502, str(exc))
    return {"message": f"Calendar refreshed: {result['eligible']} meeting(s), {result['added']} new.", "links": [_public_feed(i) for i in await cal.get_feeds(db, user.id)]}

@router.post("/connections/zoom/test")
async def zoom_test(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await rs.apply_overrides(db)
    try: info = await zoom.ping()
    except zoom.ZoomUnavailable as exc: raise HTTPException(502, str(exc))
    return {"message": f"Zoom is connected ({info.get('email') or 'account ok'})."}

@router.post("/meetings")
async def create_meeting(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Schedule a meeting. With provider 'zoom' (and Zoom set up) a real Zoom meeting is created and its join link stored."""
    title = str(payload.get("title") or "").strip()[:200]
    if not title: raise HTTPException(422, "Give the meeting a title.")
    try: start = datetime.fromisoformat(str(payload.get("start_at")).replace("Z", "+00:00"))
    except ValueError: raise HTTPException(422, "Choose a valid start date and time.")
    tz = await cal.user_timezone(db)
    if start.tzinfo is None: start = start.replace(tzinfo=tz)
    minutes = int(payload.get("duration_minutes") or 30)
    if not 5 <= minutes <= 720: raise HTTPException(422, "Duration must be between 5 minutes and 12 hours.")
    agenda = str(payload.get("agenda") or "")[:2000]
    join, ext = None, f"local:{uuid.uuid4().hex}"
    if payload.get("provider") == "zoom":
        await rs.apply_overrides(db)
        try: z = await zoom.create_meeting(title, start, minutes, str(tz), "me" if user.email == "admin@example.test" else user.email, agenda)
        except zoom.ZoomUnavailable as exc: raise HTTPException(502, str(exc))
        join, ext = z["join_url"], f"zoom:{z['id']}"
    elif payload.get("provider") == "room":
        from app.api.routes_rooms import make_room
        m0 = Meeting(owner_id=user.id, external_id=f"local:{uuid.uuid4().hex}", title=title, organizer=user.email, start_at=start.astimezone(timezone.utc), end_at=(start + timedelta(minutes=minutes)).astimezone(timezone.utc), sensitivity="normal", status="scheduled")
        db.add(m0); await db.flush()
        room, m0 = await make_room(db, user, title, str(payload.get("base_url") or ""), meeting=m0, access=payload.get("access"), passcode=payload.get("passcode"), waiting_room=payload.get("waiting_room"))
        m0.external_id = f"room:{room.code}"; await db.commit()
        note = ""
        if str(payload.get("invite") or "").strip():
            from app.services.invites import parse_recipients, build_ics
            try: inv = parse_recipients(str(payload["invite"]))
            except ValueError as exc: raise HTTPException(422, str(exc))
            acct = await cal.get_mail(db, user.id)
            if not acct: note = " Invitations were not sent: connect your mail account on the Connections page first."
            else:
                try:
                    await mailer.send(acct, inv, f"Invitation: {title}", f"{user.display_name or user.email} invited you to: {title}\nJoin: {m0.join_url}\n" + (f"Passcode: {room.passcode}\n" if room.passcode else "") + ("Sign in with your account to join.\n" if room.access == "signed_in" else "") + (agenda or ""), build_ics(m0.id, title, start, start + timedelta(minutes=minutes), acct["address"], inv, m0.join_url, (f"Passcode: {room.passcode}\n" if room.passcode else "") + agenda))
                    note = f" Invitations sent to {len(inv)}."
                except mailer.MailError as exc: note = f" The room was created but invitations could not be sent: {exc}"
        return {"id": m0.id, "join_url": m0.join_url, "access": room.access, "passcode": room.passcode, "waiting_room": room.waiting_room, "message": "Meeting room created. Share the link; it opens in any browser." + note}
    elif payload.get("join_url"):
        from app.services.meeting_links import provider_for
        u = str(payload["join_url"]).strip()
        if not provider_for(u): raise HTTPException(422, "That link is not a Zoom, Teams, Google Meet or Webex address.")
        join = u
    m = Meeting(owner_id=user.id, external_id=ext, title=title, organizer=user.email, start_at=start.astimezone(timezone.utc), end_at=(start + timedelta(minutes=minutes)).astimezone(timezone.utc),
                sensitivity="normal", join_url=join, status="scheduled")
    invited, invite_note = [], ""
    if str(payload.get("invite") or "").strip():
        from app.services.invites import parse_recipients, build_ics
        try: invited = parse_recipients(str(payload["invite"]))
        except ValueError as exc: raise HTTPException(422, str(exc))
    db.add(m); db.add(AuditLog(actor=user.email, action="meeting.create", resource_type="meeting", safe_metadata={"zoom": bool(join and ext.startswith("zoom:"))})); await db.commit()
    await db.refresh(m)
    if invited:
        acct = await cal.get_mail(db, user.id)
        if not acct: invite_note = " Invitations were not sent: connect your mail account on the Connections page first."
        else:
            try:
                ics = build_ics(m.id, title, start, start + timedelta(minutes=minutes), acct["address"], invited, join, agenda)
                body = f"{user.display_name or user.email} invited you to: {title}\nWhen: {start.astimezone(tz).strftime('%A %d %B %Y, %H:%M')} ({tz})\n" + (f"Join: {join}\n" if join else "") + (f"\n{agenda}\n" if agenda else "")
                await mailer.send(acct, invited, f"Invitation: {title}", body, ics)
                invite_note = f" Invitations sent to {len(invited)} {'person' if len(invited) == 1 else 'people'}."
            except mailer.MailError as exc: invite_note = f" The meeting was created but invitations could not be sent: {exc}"
    base_msg = "Zoom meeting created." if ext.startswith("zoom:") else "Meeting added."
    return {"id": m.id, "join_url": join, "message": base_msg + invite_note}


@router.post("/connections/mail")
async def save_mail_account(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    prov = payload.get("provider") if payload.get("provider") in mailer.PRESETS else "other"; pre = mailer.PRESETS[prov]
    address = str(payload.get("address") or "").strip().lower(); password = str(payload.get("password") or "")
    from app.services.invites import EMAIL
    if not EMAIL.match(address) or not password: raise HTTPException(422, "Enter your email address and an app password.")
    acct = {"provider": prov, "address": address, "username": str(payload.get("username") or address).strip(), "password": password,
            "smtp_host": str(payload.get("smtp_host") or pre["smtp"][0]).strip(), "smtp_port": int(payload.get("smtp_port") or pre["smtp"][1]),
            "imap_host": str(payload.get("imap_host") or pre["imap"][0]).strip(), "imap_port": int(payload.get("imap_port") or pre["imap"][1]),
            "import_invites": bool(payload.get("import_invites"))}
    try: await mailer.test(acct)
    except mailer.MailError as exc: raise HTTPException(422, str(exc))
    stored = dict(acct); stored["password"] = rs._enc(password); stored.update(ok=True, error=None, at=datetime.now(timezone.utc).isoformat())
    await cal.save_mail(db, user.id, stored)
    db.add(AuditLog(actor=user.email, action="mail.account.save", resource_type="mail", safe_metadata={"provider": prov})); await db.commit()
    msg = "Mail account connected. Invitations will be sent from it."
    if acct["import_invites"]:
        try: r = await cal.sync_calendar(db, user.id); msg += f" Calendar invitations found in your inbox were added ({r['added']} new)."
        except GraphUnavailable: pass
    return {"message": msg, "mail": await _mail_public(db, user)}

@router.delete("/connections/mail")
async def remove_mail_account(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await cal.save_mail(db, user.id, None)
    db.add(AuditLog(actor=user.email, action="mail.account.remove", resource_type="mail", safe_metadata={})); await db.commit()
    return {"mail": None}

@router.post("/connections/mail/test")
async def send_test_mail(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    acct = await cal.get_mail(db, user.id)
    if not acct: raise HTTPException(404, "Connect a mail account first.")
    try: await mailer.send(acct, [acct["address"]], "Meeting Intelligence test message", "Your mail account is connected. Meeting invitations will be sent from this address.")
    except mailer.MailError as exc: raise HTTPException(502, str(exc))
    return {"message": f"Test message sent to {acct['address']}."}

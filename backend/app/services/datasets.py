"""CSV import for every table, and the one-click mock data loader.

Rows refer to each other by readable keys (owner_email, meeting_external_id, transcript_ref) instead of internal ids,
so the same files work on any database. Existing rows are never overwritten: a row that already exists is skipped and counted.
Dates may be ISO values or relative words (today 09:30, tomorrow 14:00, -2d 10:00, +3d 16:30) so mock data never goes stale.
"""
import csv, io, json, os, re, secrets
from datetime import datetime, timedelta, timezone, time, date
from pathlib import Path
from zoneinfo import ZoneInfo
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import hash_password
from app.models import (User, LocalAccount, Meeting, Transcript, TranscriptSegment, Minutes, ActionItem, Briefing,
                        WorkflowRun, Job, AuditLog)

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000
TEMPLATE_OWNER = "sample.user@example.com"   # the sample person whose data a member receives from "Load mock data"

# table -> (admin_only, required columns, all columns, description)
TABLES: dict[str, dict] = {
 "users": dict(admin=True, required=["email"], columns=["email","display_name","role","password","is_active"],
               desc="People who can sign in (local demo accounts). Role is admin or user; password is stored hashed."),
 "meetings": dict(admin=False, required=["external_id","title","start_at"], columns=["owner_email","external_id","title","organizer","start_at","end_at","timezone","sensitivity","join_url","status","transcript_status","minutes_status"],
               desc="Calendar meetings. owner_email picks the person (admins only; members always load their own)."),
 "transcripts": dict(admin=False, required=["meeting_external_id","ref","full_text"], columns=["owner_email","meeting_external_id","ref","source_type","status","language","full_text"],
               desc="Transcript text for a meeting, identified by ref."),
 "transcript_segments": dict(admin=False, required=["transcript_ref","sequence","text"], columns=["owner_email","transcript_ref","sequence","start_seconds","end_seconds","speaker","text"],
               desc="Speaker lines of a transcript, in order."),
 "minutes": dict(admin=False, required=["meeting_external_id","content_json"], columns=["owner_email","meeting_external_id","version","review_status","edited_by","content_json"],
               desc="Draft or approved meeting minutes (content as JSON)."),
 "action_items": dict(admin=False, required=["meeting_external_id","description"], columns=["owner_email","meeting_external_id","description","owner","due_date","priority","status","evidence"],
               desc="Follow-up actions from a meeting."),
 "briefings": dict(admin=False, required=["local_date","rendered_text"], columns=["owner_email","local_date","run_type","rendered_text","generation_status","delivery_status","payload_json"],
               desc="Morning briefings, one per person, day and run type."),
 "workflow_runs": dict(admin=True, required=["correlation_id","workflow_name"], columns=["correlation_id","workflow_name","status","failure_stage","safe_error","retry_count"],
               desc="Run history entries (admin only)."),
 "jobs": dict(admin=True, required=["kind","payload_json"], columns=["kind","payload_json","status","attempts","max_attempts","last_error"],
               desc="Background job records (admin only). Mock jobs must be completed or failed; payload_json needs a mock_ref."),
 "audit_logs": dict(admin=True, required=["actor","action","resource_type"], columns=["actor","action","resource_type","resource_id","safe_metadata_json"],
               desc="Audit trail entries (admin only)."),
}
ORDER = list(TABLES)

class ImportError_(Exception): pass

def mock_dir() -> Path:
    if settings.mock_data_dir: return Path(settings.mock_data_dir)
    return Path(__file__).resolve().parents[3] / "docs" / "mock-data"

# ---------- value parsing ----------
def parse_when(value: str, tz: ZoneInfo) -> datetime:
    v = (value or "").strip()
    m = re.fullmatch(r"(today|tomorrow|yesterday|[+-]\d+d)(?:\s+(\d{1,2}):(\d{2}))?", v, re.I)
    if m:
        word = m.group(1).lower(); delta = {"today": 0, "tomorrow": 1, "yesterday": -1}.get(word)
        if delta is None: delta = int(word[:-1])
        d = datetime.now(tz).date() + timedelta(days=delta)
        return datetime.combine(d, time(int(m.group(2) or 9), int(m.group(3) or 0)), tzinfo=tz).astimezone(timezone.utc)
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"'{value}' is not a date/time (use 2026-10-14 09:30 or 'today 09:30')")
    return (dt.replace(tzinfo=tz) if dt.tzinfo is None else dt).astimezone(timezone.utc)

def parse_day(value: str, tz: ZoneInfo) -> str:
    v = (value or "").strip().lower()
    m = re.fullmatch(r"(today|tomorrow|yesterday|[+-]\d+d)", v)
    if m:
        delta = {"today": 0, "tomorrow": 1, "yesterday": -1}.get(v)
        if delta is None: delta = int(v[:-1])
        return (datetime.now(tz).date() + timedelta(days=delta)).isoformat()
    try: return date.fromisoformat(v).isoformat()
    except ValueError: raise ValueError(f"'{value}' is not a date (use 2026-10-14 or 'today')")

def as_bool(v, default=True) -> bool:
    s = str(v or "").strip().lower()
    return default if s == "" else s in ("1", "true", "yes", "y", "on")

def as_int(v, default=0) -> int:
    s = str(v or "").strip()
    if s == "": return default
    try: return int(float(s))
    except ValueError: raise ValueError(f"'{v}' is not a whole number")

def as_float(v):
    s = str(v or "").strip()
    if s == "": return None
    try: return float(s)
    except ValueError: raise ValueError(f"'{v}' is not a number")

def as_json(v, kind=dict):
    s = str(v or "").strip()
    if not s: return kind()
    try: out = json.loads(s)
    except json.JSONDecodeError: raise ValueError("JSON column is not valid JSON")
    if not isinstance(out, kind): raise ValueError("JSON column has the wrong shape")
    return out

# ---------- CSV reading ----------
def read_csv(data: bytes, table: str) -> list[dict]:
    if len(data) > MAX_BYTES: raise ImportError_("File is larger than 5 MB.")
    try: text = data.decode("utf-8-sig")
    except UnicodeDecodeError: raise ImportError_("File must be UTF-8 text (save as 'CSV UTF-8').")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames: raise ImportError_("The file is empty.")
    names = [(n or "").strip().lower() for n in reader.fieldnames]
    spec = TABLES[table]
    missing = [c for c in spec["required"] if c not in names]
    if missing: raise ImportError_("Missing column(s): " + ", ".join(missing) + ". Expected columns: " + ", ".join(spec["columns"]) + ".")
    rows = []
    for raw in reader:
        row = {(k or "").strip().lower(): (v or "").strip() if isinstance(v, str) else "" for k, v in raw.items() if k is not None}
        if not any(row.values()): continue
        rows.append(row)
        if len(rows) > MAX_ROWS: raise ImportError_(f"More than {MAX_ROWS} rows. Split the file.")
    return rows

def template_csv(table: str) -> str:
    cols = TABLES[table]["columns"]; out = io.StringIO(); w = csv.writer(out); w.writerow(cols)
    f = mock_dir() / f"{table}.csv"
    if f.is_file():
        try:
            r = list(csv.DictReader(io.StringIO(f.read_text(encoding="utf-8-sig"))))
            if r: w.writerow([r[0].get(c, "") for c in cols])
        except Exception: pass
    return out.getvalue()

# ---------- shared user creation ----------
async def create_local_user(db: AsyncSession, email: str, name: str, password: str, role: str, active: bool = True) -> User:
    email = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254: raise ValueError("Enter a valid email address.")
    if email == "admin@example.test": raise ValueError("That email is reserved for the built-in administrator.")
    if role not in ("admin", "user"): raise ValueError("Role must be admin or user.")
    if password and not (8 <= len(password) <= 128): raise ValueError("Password must be 8 to 128 characters.")
    if (await db.execute(select(LocalAccount).where(LocalAccount.email == email))).scalar_one_or_none(): raise ValueError("A user with this email already exists.")
    acct = LocalAccount(email=email, display_name=(name or email)[:200], password_hash=hash_password(password or secrets.token_urlsafe(24)))
    db.add(acct); await db.flush()
    user = User(entra_subject=acct.id, email=email, display_name=acct.display_name, role=role, role_override="admin" if role == "admin" else None, is_active=active)
    db.add(user); await db.flush()
    return user

# ---------- importer ----------
class Ctx:
    def __init__(self, db: AsyncSession, actor: User, tz: ZoneInfo, force_owner: bool):
        self.db, self.actor, self.tz, self.force_owner = db, actor, tz, force_owner
        self._users: dict[str, User | None] = {}; self._meetings: dict[tuple, Meeting | None] = {}; self._tx: dict[tuple, Transcript | None] = {}
    async def owner(self, row: dict) -> User:
        email = (row.get("owner_email") or "").strip().lower()
        if self.force_owner or not email: return self.actor
        if email == "admin@example.test" and self.actor.role == "admin": return self.actor   # the built-in admin is whoever is signed in as admin
        if email not in self._users:
            self._users[email] = (await self.db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        u = self._users[email]
        if not u: raise ValueError(f"owner_email '{email}' is not a known user (load users first)")
        return u
    async def meeting(self, owner: User, external_id: str) -> Meeting:
        key = (owner.id, external_id)
        if key not in self._meetings:
            self._meetings[key] = (await self.db.execute(select(Meeting).where(Meeting.owner_id == owner.id, Meeting.external_id == external_id))).scalar_one_or_none()
        m = self._meetings[key]
        if not m: raise ValueError(f"meeting '{external_id}' not found for {owner.email} (load meetings first)")
        return m
    async def transcript(self, owner: User, ref: str) -> Transcript:
        key = (owner.id, ref)
        if key not in self._tx:
            self._tx[key] = (await self.db.execute(select(Transcript).join(Meeting).where(Meeting.owner_id == owner.id, Transcript.source_reference == ref))).scalars().first()
        t = self._tx[key]
        if not t: raise ValueError(f"transcript '{ref}' not found for {owner.email} (load transcripts first)")
        return t

async def _exists(db, stmt) -> bool:
    return (await db.execute(stmt.limit(1))).first() is not None

async def _row(ctx: Ctx, table: str, r: dict) -> bool:
    """Insert one row. Returns True when inserted, False when it already existed."""
    db = ctx.db
    if table == "users":
        if not settings.is_local_demo: raise ValueError("Users are managed in Microsoft Entra in this mode")
        if (await db.execute(select(User).where(User.email == r["email"].lower()))).scalar_one_or_none(): return False
        role = (r.get("role") or "user").lower()
        await create_local_user(db, r["email"], r.get("display_name", ""), r.get("password", ""), role, as_bool(r.get("is_active"), True)); return True
    if table == "workflow_runs":
        if await _exists(db, select(WorkflowRun.id).where(WorkflowRun.correlation_id == r["correlation_id"], WorkflowRun.workflow_name == r["workflow_name"])): return False
        db.add(WorkflowRun(correlation_id=r["correlation_id"][:36], workflow_name=r["workflow_name"], status=r.get("status") or "completed", failure_stage=r.get("failure_stage") or None,
                           safe_error=r.get("safe_error") or None, retry_count=as_int(r.get("retry_count")))); return True
    if table == "jobs":
        payload = as_json(r["payload_json"]); ref = payload.get("mock_ref")
        if not ref: raise ValueError("payload_json needs a \"mock_ref\" value so the row can be recognised on re-import")
        status = r.get("status") or "completed"
        if status not in ("completed", "failed", "cancelled"): raise ValueError("mock jobs must have status completed, failed or cancelled")
        for j in (await db.execute(select(Job).where(Job.kind == r["kind"]))).scalars():
            if (j.payload or {}).get("mock_ref") == ref: return False
        db.add(Job(kind=r["kind"], payload=payload, status=status, attempts=as_int(r.get("attempts")), max_attempts=as_int(r.get("max_attempts"), 5), last_error=r.get("last_error") or None)); return True
    if table == "audit_logs":
        rid = r.get("resource_id") or None
        if rid and await _exists(db, select(AuditLog.id).where(AuditLog.actor == r["actor"], AuditLog.action == r["action"], AuditLog.resource_id == rid)): return False
        db.add(AuditLog(actor=r["actor"], action=r["action"], resource_type=r["resource_type"], resource_id=rid, safe_metadata=as_json(r.get("safe_metadata_json")))); return True

    owner = await ctx.owner(r)
    if table == "meetings":
        if await _exists(db, select(Meeting.id).where(Meeting.owner_id == owner.id, Meeting.external_id == r["external_id"])): return False
        start = parse_when(r["start_at"], ctx.tz); end = parse_when(r["end_at"], ctx.tz) if r.get("end_at") else start + timedelta(minutes=30)
        if end <= start: raise ValueError("end_at must be after start_at")
        sens = (r.get("sensitivity") or "normal").lower()
        db.add(Meeting(owner_id=owner.id, external_id=r["external_id"][:500], title=r["title"][:500], organizer=r.get("organizer", "")[:320], start_at=start, end_at=end,
                       timezone=r.get("timezone") or str(ctx.tz), sensitivity=sens, join_url=r.get("join_url") or None, status=r.get("status") or "scheduled",
                       transcript_status=r.get("transcript_status") or "not_available", minutes_status=r.get("minutes_status") or "not_started"))
        await db.flush(); ctx._meetings.pop((owner.id, r["external_id"]), None); return True
    if table == "transcripts":
        m = await ctx.meeting(owner, r["meeting_external_id"])
        if await _exists(db, select(Transcript.id).where(Transcript.meeting_id == m.id, Transcript.source_reference == r["ref"])): return False
        db.add(Transcript(meeting_id=m.id, source_type=r.get("source_type") or "mock_fixture", status=r.get("status") or "ready", language=r.get("language") or "en", full_text=r["full_text"], source_reference=r["ref"]))
        await db.flush(); ctx._tx.pop((owner.id, r["ref"]), None); return True
    if table == "transcript_segments":
        t = await ctx.transcript(owner, r["transcript_ref"]); seq = as_int(r["sequence"])
        if await _exists(db, select(TranscriptSegment.id).where(TranscriptSegment.transcript_id == t.id, TranscriptSegment.sequence == seq)): return False
        db.add(TranscriptSegment(transcript_id=t.id, sequence=seq, start_seconds=as_float(r.get("start_seconds")), end_seconds=as_float(r.get("end_seconds")), speaker=r.get("speaker") or None, text=r["text"])); return True
    if table == "minutes":
        m = await ctx.meeting(owner, r["meeting_external_id"]); ver = as_int(r.get("version"), 1)
        if await _exists(db, select(Minutes.id).where(Minutes.meeting_id == m.id, Minutes.version == ver)): return False
        review = r.get("review_status") or "draft"
        db.add(Minutes(meeting_id=m.id, version=ver, content=as_json(r["content_json"]), review_status=review, edited_by=r.get("edited_by") or None,
                       approved_at=datetime.now(timezone.utc) if review == "approved" else None)); return True
    if table == "action_items":
        m = await ctx.meeting(owner, r["meeting_external_id"])
        if await _exists(db, select(ActionItem.id).where(ActionItem.meeting_id == m.id, ActionItem.description == r["description"])): return False
        due = r.get("due_date") or None
        if due:
            try: due = parse_day(due, ctx.tz)
            except ValueError: pass          # free text such as "Friday" is allowed
        db.add(ActionItem(meeting_id=m.id, description=r["description"], owner=r.get("owner") or None, due_date=due, priority=r.get("priority") or "normal", status=r.get("status") or "needs_review", evidence=r.get("evidence") or None)); return True
    if table == "briefings":
        day = parse_day(r["local_date"], ctx.tz); run = r.get("run_type") or "demo"
        if await _exists(db, select(Briefing.id).where(Briefing.user_id == owner.id, Briefing.local_date == day, Briefing.run_type == run)): return False
        text = r["rendered_text"]
        db.add(Briefing(user_id=owner.id, local_date=day, run_type=run, payload=as_json(r.get("payload_json")) or {"fixture": True}, rendered_text=text, word_count=len(text.split()),
                        generation_status=r.get("generation_status") or "generated", delivery_status=r.get("delivery_status") or "mock_not_delivered")); return True
    raise ValueError("Unknown table")

async def import_rows(db: AsyncSession, table: str, rows: list[dict], actor: User, tz: ZoneInfo, only_owner: str | None = None) -> dict:
    spec = TABLES[table]
    if spec["admin"] and actor.role != "admin": raise ImportError_(f"Only an administrator can import {table}.")
    force = actor.role != "admin"
    ctx = Ctx(db, actor, tz, force)
    res = {"inserted": 0, "skipped": 0, "errors": []}
    for n, r in enumerate(rows, start=2):                    # row 1 is the header
        if only_owner is not None and "owner_email" in spec["columns"] and (r.get("owner_email") or "").lower() != only_owner: continue
        try:
            async with db.begin_nested():
                for c in spec["required"]:
                    if not r.get(c): raise ValueError(f"'{c}' is required")
                if await _row(ctx, table, r): res["inserted"] += 1
                else: res["skipped"] += 1
        except ValueError as exc:
            if len(res["errors"]) < 100: res["errors"].append({"row": n, "message": str(exc)})
            else: res["errors_truncated"] = True
        except Exception as exc:
            if len(res["errors"]) < 100: res["errors"].append({"row": n, "message": "Row could not be saved"})
    await db.commit()
    return res

async def user_tz(db: AsyncSession) -> ZoneInfo:
    from app.services.calendar_sync import user_timezone
    return await user_timezone(db)

def summarize(result: dict) -> str:
    parts = []; ins = sum(t["inserted"] for t in result.values()); sk = sum(t["skipped"] for t in result.values()); er = sum(len(t["errors"]) for t in result.values())
    for t, v in result.items():
        if v["inserted"]: parts.append(f"{v['inserted']} {t.replace('_', ' ')}")
    msg = ("Added " + ", ".join(parts) + ".") if parts else "Nothing new was added."
    if sk: msg += f" {sk} row(s) already existed and were left as they were."
    if er: msg += f" {er} row(s) had problems."
    return msg

async def reset_mock(db: AsyncSession, actor: User) -> None:
    """Remove previously loaded mock rows (meetings whose id starts with demo-, demo briefings, mock jobs/runs for admins)."""
    q = select(Meeting.id).where(Meeting.external_id.like("demo-%"))
    if actor.role != "admin": q = q.where(Meeting.owner_id == actor.id)
    ids = [x for (x,) in (await db.execute(q)).all()]
    if ids:
        tids = [x for (x,) in (await db.execute(select(Transcript.id).where(Transcript.meeting_id.in_(ids)))).all()]
        if tids: await db.execute(delete(TranscriptSegment).where(TranscriptSegment.transcript_id.in_(tids)))
        await db.execute(delete(Transcript).where(Transcript.meeting_id.in_(ids)))
        await db.execute(delete(Minutes).where(Minutes.meeting_id.in_(ids)))
        await db.execute(delete(ActionItem).where(ActionItem.meeting_id.in_(ids)))
        await db.execute(delete(Meeting).where(Meeting.id.in_(ids)))
    bq = delete(Briefing).where(Briefing.run_type == "demo")
    if actor.role != "admin": bq = bq.where(Briefing.user_id == actor.id)
    await db.execute(bq)
    if actor.role == "admin":
        await db.execute(delete(WorkflowRun).where(WorkflowRun.correlation_id.like("demo-%")))
        for j in (await db.execute(select(Job))).scalars():
            if (j.payload or {}).get("mock_ref"): await db.delete(j)
    await db.commit()

async def load_mock(db: AsyncSession, actor: User, reset: bool = False) -> dict:
    d = mock_dir()
    if not d.is_dir() or not any((d / f"{t}.csv").is_file() for t in ORDER):
        raise ImportError_("Mock data files were not found. Expected CSV files in: " + str(d))
    if reset: await reset_mock(db, actor)
    tz = await user_tz(db); result = {}
    is_admin = actor.role == "admin"
    for table in ORDER:
        spec = TABLES[table]; f = d / f"{table}.csv"
        if not f.is_file() or (spec["admin"] and not is_admin): continue
        rows = read_csv(f.read_bytes(), table)
        result[table] = await import_rows(db, table, rows, actor, tz, only_owner=None if is_admin else TEMPLATE_OWNER)
    return result

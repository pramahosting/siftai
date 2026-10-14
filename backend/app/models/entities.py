import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Boolean, Integer, ForeignKey, UniqueConstraint, Index, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

def now_utc(): return datetime.now(timezone.utc)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entra_subject: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(40), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    role_override: Mapped[str | None] = mapped_column(String(40), nullable=True)   # set by an administrator
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class LocalAccount(Base):
    """Sign-up accounts for local demo mode only (Entra mode uses Microsoft sign-in)."""
    __tablename__ = "local_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (UniqueConstraint("owner_id", "external_id", name="uq_meeting_owner_external"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500))
    organizer: Mapped[str] = mapped_column(String(320), default="")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    sensitivity: Mapped[str] = mapped_column(String(30), default="normal")
    join_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="scheduled")
    transcript_status: Mapped[str] = mapped_column(String(40), default="not_available")
    minutes_status: Mapped[str] = mapped_column(String(40), default="not_started")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="ready")
    language: Mapped[str] = mapped_column(String(20), default="en")
    full_text: Mapped[str] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    segments: Mapped[list["TranscriptSegment"]] = relationship(cascade="all, delete-orphan", order_by="TranscriptSegment.sequence")

class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transcript_id: Mapped[str] = mapped_column(ForeignKey("transcripts.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    start_seconds: Mapped[float | None] = mapped_column(nullable=True)
    end_seconds: Mapped[float | None] = mapped_column(nullable=True)
    speaker: Mapped[str | None] = mapped_column(String(200), nullable=True)
    text: Mapped[str] = mapped_column(Text)

class Minutes(Base):
    __tablename__ = "meeting_minutes"
    __table_args__ = (UniqueConstraint("meeting_id", "version", name="uq_minutes_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    source_job_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[dict] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(30), default="draft")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    edited_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class ActionItem(Base):
    __tablename__ = "action_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(320), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(30), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    status: Mapped[str] = mapped_column(String(30), default="needs_review")
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class Briefing(Base):
    __tablename__ = "briefings"
    __table_args__ = (UniqueConstraint("user_id", "local_date", "run_type", name="uq_briefing_idempotency"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    local_date: Mapped[str] = mapped_column(String(10))
    run_type: Mapped[str] = mapped_column(String(30), default="scheduled")
    payload: Mapped[dict] = mapped_column(JSON)
    rendered_text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    generation_status: Mapped[str] = mapped_column(String(30), default="generated")
    delivery_status: Mapped[str] = mapped_column(String(30), default="pending")
    delivery_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    correlation_id: Mapped[str] = mapped_column(String(36), index=True)
    workflow_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    failure_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safe_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "available_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class IntegrationSetting(Base):
    __tablename__ = "integration_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor: Mapped[str] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Room(Base):
    """A built-in video meeting room. The room code in the link is the secret that lets people in."""
    __tablename__ = "rooms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    host_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    meeting_id: Mapped[str | None] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    allow_guests: Mapped[bool] = mapped_column(Boolean, default=True)
    access: Mapped[str] = mapped_column(String(16), default="open")          # open | passcode | signed_in
    passcode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    waiting_room: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class RoomRecording(Base):
    __tablename__ = "room_recordings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    has_video: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

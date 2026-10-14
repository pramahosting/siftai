from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict, field_validator

class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    model_config = ConfigDict(from_attributes=True)

class MeetingOut(BaseModel):
    id: str
    title: str
    organizer: str
    start_at: datetime
    end_at: datetime
    sensitivity: str
    status: str
    transcript_status: str
    join_url: str | None = None
    minutes_status: str
    model_config = ConfigDict(from_attributes=True)

    @field_validator("start_at","end_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        # SQLite returns naive datetimes; they are stored as UTC, so make that explicit for clients.
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v

class BriefingPreview(BaseModel):
    local_date: str
    rendered_text: str
    word_count: int
    eligible_meetings: int
    verified: bool

class DeliveryCallback(BaseModel):
    briefing_id: str
    status: str = Field(pattern="^(sent|failed|unknown)$")
    reference: str | None = None

class MinutesUpdate(BaseModel):
    content: dict
    review_status: str = Field(default="draft", pattern="^(draft|reviewed|approved)$")

class ActionUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(proposed|needs_review|assigned|in_progress|completed)$")
    owner: str | None = None
    due_date: str | None = None
    priority: str | None = Field(default=None, pattern="^(low|normal|high)$")

class SettingsUpdate(BaseModel):
    timezone: str | None = None
    briefing_time: str | None = None
    lookback_days: int | None = Field(default=None, ge=1, le=14)
    human_review_required: bool | None = None
    transcript_retention_days: int | None = Field(default=None, ge=1, le=3650)
    minutes_retention_days: int | None = Field(default=None, ge=0, le=3650)
    sensitive_context_enabled: bool | None = None

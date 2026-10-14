from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_env: str = "development"
    app_name: str = "AI Meeting Intelligence Platform"
    database_url: str = "postgresql+asyncpg://meeting:meeting@db:5432/meeting_intelligence"
    frontend_origin: str = "http://localhost:5173"
    auth_mode: str = "local"
    allow_local_auth: bool = True
    allow_signup: bool = True
    local_auth_secret: str = "development-only-change-before-deploy"
    settings_encryption_key: str = ""
    entra_tenant_id: str = ""
    entra_api_audience: str = ""
    entra_admin_role: str = "MeetingIntelligence.Admin"
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_user_id: str = ""
    graph_transcript_enabled: bool = False
    zoom_account_id: str = ""
    zoom_client_id: str = ""
    zoom_client_secret: str = ""
    calendar_feed_allow_private: bool = False
    local_admin_password: str = "Meeting$1"
    ice_servers: str = "stun:stun.l.google.com:19302"
    turn_username: str = ""
    turn_credential: str = ""
    room_max_people: int = 25
    room_default_access: str = "open"
    room_default_waiting: bool = True
    graph_context_enabled: bool = False
    automation_user_email: str = "admin@example.test"
    azure_openai_endpoint: str = ""
    azure_openai_auth: str = "key"
    azure_openai_api_key: str = ""
    azure_openai_chat_deployment: str = ""
    azure_openai_transcription_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_use_temperature: bool = True
    automation_shared_token: str = ""
    default_timezone: str = "Australia/Sydney"
    briefing_time: str = "06:55"
    calendar_sync_minutes: int = 30
    db_pool_size: int = 10
    mock_data_enabled: bool = True
    load_mock_on_start: bool = True
    calendar_on_start: bool = True
    machine_calendar_allowed: bool = True
    machine_calendar_dir: str = ""
    mock_data_dir: str = ""
    lookback_days: int = 3
    max_briefing_words: int = 399
    admin_emails: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    error_email_to: str = ""
    audio_storage_dir: str = "/data/audio"
    audio_max_bytes: int = 25 * 1024 * 1024
    audio_retention_days: int = 0
    context_retention_days: int = 7

    @property
    def is_local_demo(self) -> bool:
        return self.app_env == "development" and self.auth_mode == "local" and self.allow_local_auth

    @property
    def admins(self) -> set[str]:
        return {value.strip().lower() for value in self.admin_emails.split(",") if value.strip()}

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

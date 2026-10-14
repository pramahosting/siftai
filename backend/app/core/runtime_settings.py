"""Admin-editable integration settings.

Values saved from the Admin settings page are stored in the database (secrets are
encrypted at rest) and applied on top of the environment/.env defaults for both the
API and the background worker. Removing a saved value falls back to the environment.
"""
import base64, hashlib, logging
from urllib.parse import urlsplit
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models import IntegrationSetting

log = logging.getLogger("meeting_platform")
STORE_KEY = "integration_values"
AZURE_HOSTS = (".openai.azure.com", ".cognitiveservices.azure.com", ".openai.azure.us", ".cognitiveservices.azure.us")  # keys are only ever sent to Azure hosts

# kind: text | secret | bool | number | email | url | select
FIELDS = [
 {"key":"azure_openai_endpoint","label":"Azure OpenAI endpoint","group":"Microsoft Copilot AI (Azure OpenAI)","kind":"url","help":"Your resource URL, for example https://my-resource.openai.azure.com (Azure portal → your Azure OpenAI resource → Keys and Endpoint)."},
 {"key":"azure_openai_auth","label":"Sign-in method for the AI service","group":"Microsoft Copilot AI (Azure OpenAI)","kind":"select","options":["key","entra"],"help":"key = API key below. entra = the Microsoft client ID/secret from the Microsoft section (needs the Cognitive Services OpenAI User role on the resource)."},
 {"key":"azure_openai_api_key","label":"Azure OpenAI API key","group":"Microsoft Copilot AI (Azure OpenAI)","kind":"secret","help":"Only used when the sign-in method is key."},
 {"key":"azure_openai_chat_deployment","label":"Chat model deployment name","group":"Microsoft Copilot AI (Azure OpenAI)","kind":"text","help":"Name of your deployed chat model, for example gpt-4o or gpt-4.1. It must support structured output."},
 {"key":"azure_openai_transcription_deployment","label":"Transcription deployment name (optional)","group":"Microsoft Copilot AI (Azure OpenAI)","kind":"text","help":"Name of a deployed Whisper model. Only needed to transcribe uploaded audio."},
 {"key":"azure_openai_api_version","label":"API version","group":"Microsoft Copilot AI (Azure OpenAI)","kind":"text","help":"Leave as the default unless your administrator says otherwise."},
 {"key":"azure_openai_use_temperature","label":"Send temperature 0 for steadier output (turn off for o-series / GPT-5 reasoning models)","group":"Microsoft Copilot AI (Azure OpenAI)","kind":"bool"},
 {"key":"entra_tenant_id","label":"Microsoft tenant ID","group":"Microsoft Entra and Graph","kind":"text","help":"Directory (tenant) ID of your Microsoft Entra tenant."},
 {"key":"entra_api_audience","label":"API audience","group":"Microsoft Entra and Graph","kind":"text","help":"For example api://<client-id>."},
 {"key":"entra_admin_role","label":"Administrator app role","group":"Microsoft Entra and Graph","kind":"text"},
 {"key":"admin_emails","label":"Administrator emails","group":"Microsoft Entra and Graph","kind":"text","help":"Comma-separated list of administrator sign-in emails."},
 {"key":"graph_client_id","label":"Microsoft client ID","group":"Microsoft Entra and Graph","kind":"text"},
 {"key":"graph_client_secret","label":"Microsoft client secret","group":"Microsoft Entra and Graph","kind":"secret"},
 {"key":"graph_user_id","label":"Calendar user (ID or email)","group":"Microsoft Entra and Graph","kind":"text"},
 {"key":"graph_transcript_enabled","label":"Fetch official Teams transcripts","group":"Microsoft Entra and Graph","kind":"bool"},
 {"key":"graph_context_enabled","label":"Use email/chat context in briefings","group":"Microsoft Entra and Graph","kind":"bool"},
 {"key":"ice_servers","label":"STUN / TURN servers for video meetings (comma-separated)","group":"Video meetings","kind":"text","help":"Example: stun:stun.l.google.com:19302,turn:turn.example.com:3478. STUN works on most networks; add a TURN server for people behind strict firewalls."},
 {"key":"turn_username","label":"TURN username (optional)","group":"Video meetings","kind":"text"},
 {"key":"turn_credential","label":"TURN password (optional)","group":"Video meetings","kind":"secret"},
 {"key":"room_max_people","label":"Maximum people in one video meeting","group":"Video meetings","kind":"number","min":2,"max":100,"help":"Built-in meetings connect everyone directly to everyone, so each person needs more bandwidth as the room grows. Up to about 8 is smooth on ordinary connections; above that, expect to need good networks and computers."},
 {"key":"room_default_access","label":"Who can join a new video meeting by default","group":"Video meetings","kind":"select","options":["open","passcode","signed_in"],"help":"open = anyone with the link; passcode = link plus a short passcode; signed_in = only people with an account here. The host can change it for each meeting."},
 {"key":"room_default_waiting","label":"Waiting room on by default (the host admits people one by one)","group":"Video meetings","kind":"bool"},
 {"key":"zoom_account_id","label":"Zoom account ID","group":"Zoom","kind":"text","help":"Zoom Marketplace > Develop > Build App > Server-to-Server OAuth. Copy the Account ID, Client ID and Client secret. Scopes needed: meeting:read, meeting:write, cloud_recording:read (and user:read)."},
 {"key":"zoom_client_id","label":"Zoom client ID","group":"Zoom","kind":"text"},
 {"key":"zoom_client_secret","label":"Zoom client secret","group":"Zoom","kind":"secret"},
 {"key":"calendar_feed_allow_private","label":"Allow calendar links that point to this computer or private network (normally off)","group":"Calendar","kind":"bool","help":"Calendar links (Google, Yahoo, Outlook.com, iCloud) are only fetched from public https addresses unless this is on."},
 {"key":"machine_calendar_allowed","label":"Allow reading the calendar on the computer running this app (Outlook on Windows, Calendar on Mac, or .ics files)","group":"Calendar","kind":"bool","help":"Each person is still asked for permission before it is used, and only from this computer. Used when no Microsoft 365 calendar is connected."},
 {"key":"calendar_sync_minutes","label":"Automatic calendar refresh (minutes)","group":"Calendar","kind":"number","min":0,"max":1440,"help":"How often the calendar is pulled in automatically. 0 turns automatic refresh off."},
 {"key":"automation_shared_token","label":"Automation token","group":"Power Automate","kind":"secret","help":"Bearer token Power Automate sends to call the briefing endpoints."},
 {"key":"automation_user_email","label":"Automation user email","group":"Power Automate","kind":"email"},
 {"key":"smtp_host","label":"SMTP host","group":"Failure email (optional)","kind":"text"},
 {"key":"smtp_port","label":"SMTP port","group":"Failure email (optional)","kind":"number","min":1,"max":65535},
 {"key":"smtp_user","label":"SMTP user","group":"Failure email (optional)","kind":"text"},
 {"key":"smtp_password","label":"SMTP password","group":"Failure email (optional)","kind":"secret"},
 {"key":"smtp_from","label":"From address","group":"Failure email (optional)","kind":"email"},
 {"key":"error_email_to","label":"Send failures to","group":"Failure email (optional)","kind":"email"},
 {"key":"mock_data_enabled","label":"Allow mock data (sample data, one-click load and CSV upload)","group":"Mock data","kind":"bool","help":"Turn off to hide Load mock data and CSV upload for everyone and refuse those requests. Recommended off in production."},
 {"key":"load_mock_on_start","label":"Load the mock data CSV files automatically the first time the app starts","group":"Startup","kind":"bool","help":"Needs 'Allow mock data'. Runs once, before the app starts serving. Takes effect at the next start."},
 {"key":"calendar_on_start","label":"At start, pick up the calendar on this computer for the administrator and sync it","group":"Startup","kind":"bool","help":"Needs 'Allow reading the calendar on the computer'. Other people are still asked before their calendar is used. Takes effect at the next start."}
]
BY_KEY={f["key"]:f for f in FIELDS}
_ENV_DEFAULTS={f["key"]:getattr(settings,f["key"]) for f in FIELDS}   # snapshot of env/.env values

def _fernet()->Fernet:
    secret=(getattr(settings,"settings_encryption_key","") or settings.local_auth_secret).encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))

def _enc(v:str)->str: return "enc:"+_fernet().encrypt(v.encode()).decode()
def _dec(v:str)->str:
    if not isinstance(v,str) or not v.startswith("enc:"): return v
    try: return _fernet().decrypt(v[4:].encode()).decode()
    except InvalidToken:
        log.warning("A saved secret could not be decrypted (encryption key changed?); using environment value."); return ""

def _coerce(f,raw):
    k=f["kind"]
    if k=="bool":
        if isinstance(raw,bool): return raw
        return str(raw).strip().lower() in ("1","true","yes","on")
    if k=="number":
        try: n=int(raw)
        except (TypeError,ValueError): raise ValueError(f"{f['label']} must be a whole number")
        if not (f.get("min",0)<=n<=f.get("max",10**9)): raise ValueError(f"{f['label']} must be between {f.get('min',0)} and {f.get('max')}")
        return n
    s=str(raw).strip()
    if k=="select":
        if s not in f.get("options",[]): raise ValueError(f"{f['label']} must be one of: "+", ".join(f.get("options",[])))
        return s
    if k=="url":
        if s=="": return s
        u=urlsplit(s); host=(u.hostname or "").lower()
        if u.scheme!="https" or not any(host.endswith(x) for x in AZURE_HOSTS) or u.username or u.password:
            raise ValueError(f"{f['label']} must be an https Azure OpenAI address such as https://my-resource.openai.azure.com")
        return f"https://{host}"
    if k=="email" and s and ("@" not in s or " " in s): raise ValueError(f"{f['label']} must be an email address")
    if len(s)>500: raise ValueError(f"{f['label']} is too long")
    return s

def mask(value:str)->str:
    if not value: return ""
    return "••••••••"+value[-4:] if len(value)>=12 else "••••••••"

async def _saved(db:AsyncSession)->dict:
    row=(await db.execute(select(IntegrationSetting).where(IntegrationSetting.key==STORE_KEY))).scalar_one_or_none()
    return dict(row.value) if row and row.value else {}

async def apply_overrides(db:AsyncSession)->None:
    """Apply saved values over environment defaults (called at startup, after save, and by the worker)."""
    saved=await _saved(db)
    for f in FIELDS:
        k=f["key"]
        if k in saved:
            try: value=_dec(saved[k]) if f["kind"]=="secret" else saved[k]
            except Exception: continue
            if f["kind"]=="secret" and value=="": value=_ENV_DEFAULTS[k]
            setattr(settings,k,value)
        else: setattr(settings,k,_ENV_DEFAULTS[k])

def database_display()->str:
    url=settings.database_url
    try:
        u=urlsplit(url)
        if u.scheme.startswith("sqlite"): return "SQLite file: "+(u.path.lstrip("/") or url)
        host=u.hostname or ""; port=f":{u.port}" if u.port else ""; user=f"{u.username}:••••@" if u.username else ""
        return f"{u.scheme.split('+')[0]}://{user}{host}{port}{u.path}"
    except Exception: return "Configured"

async def describe(db:AsyncSession)->list[dict]:
    saved=await _saved(db); out=[]
    for f in FIELDS:
        k=f["key"]; cur=getattr(settings,k); is_secret=f["kind"]=="secret"
        source="saved" if k in saved else ("environment" if _ENV_DEFAULTS[k] not in ("",None,False) else "default")
        item={"key":k,"label":f["label"],"group":f["group"],"kind":f["kind"],"help":f.get("help",""),"source":source,"is_set":bool(cur) if f["kind"]!="bool" else True}
        item["value"]=mask(str(cur)) if is_secret else cur
        if "options" in f: item["options"]=f["options"]
        out.append(item)
    return out

async def save(db:AsyncSession,values:dict)->list[str]:
    """values: key -> new value; None resets to the environment default; empty secret = unchanged."""
    saved=await _saved(db); changed=[]
    for k,raw in values.items():
        f=BY_KEY.get(k)
        if not f: raise ValueError(f"Unknown setting: {k}")
        if raw is None:
            if k in saved: del saved[k]; changed.append(k)
            continue
        if f["kind"]=="secret":
            if str(raw).strip()=="": continue
            v=_coerce(f,raw); saved[k]=_enc(v)
        else: saved[k]=_coerce(f,raw)
        changed.append(k)
    row=(await db.execute(select(IntegrationSetting).where(IntegrationSetting.key==STORE_KEY))).scalar_one_or_none()
    if row: row.value=saved
    else: db.add(IntegrationSetting(key=STORE_KEY,value=saved))
    await db.flush(); await apply_overrides(db)
    return changed

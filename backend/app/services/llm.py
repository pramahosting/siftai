"""Microsoft Azure OpenAI (the model service behind Microsoft Copilot) client.

Uses plain HTTPS so it adds no compiled dependencies. Supports API-key or Microsoft Entra
(client-credentials) authentication, structured JSON output validated with pydantic, and
speech-to-text through an Azure OpenAI Whisper deployment.
"""
import asyncio, json, logging, time
import httpx
from pydantic import BaseModel, ValidationError
from app.core.config import settings

log = logging.getLogger("meeting_platform")

class AIUnavailable(RuntimeError): pass

def _endpoint() -> str: return (settings.azure_openai_endpoint or "").strip().rstrip("/")

def ai_configured() -> bool:
    if not (_endpoint() and settings.azure_openai_chat_deployment): return False
    if settings.azure_openai_auth == "entra":
        return bool(settings.entra_tenant_id and settings.graph_client_id and settings.graph_client_secret)
    return bool(settings.azure_openai_api_key)

def transcription_configured() -> bool:
    return bool(_endpoint() and settings.azure_openai_transcription_deployment) and (
        bool(settings.entra_tenant_id and settings.graph_client_id and settings.graph_client_secret)
        if settings.azure_openai_auth == "entra" else bool(settings.azure_openai_api_key))

_token = {"value": "", "exp": 0.0}

async def _entra_token() -> str:
    if _token["value"] and time.time() < _token["exp"] - 120: return _token["value"]
    gov = ".azure.us" in _endpoint()
    scope = "https://cognitiveservices.azure.us/.default" if gov else "https://cognitiveservices.azure.com/.default"
    authority = "login.microsoftonline.us" if gov else "login.microsoftonline.com"
    data = {"client_id": settings.graph_client_id, "client_secret": settings.graph_client_secret, "grant_type": "client_credentials", "scope": scope}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"https://{authority}/{settings.entra_tenant_id}/oauth2/v2.0/token", data=data)
    if r.status_code >= 400: raise AIUnavailable(f"Microsoft sign-in for the AI service failed ({r.status_code})")
    body = r.json(); _token.update(value=body["access_token"], exp=time.time() + int(body.get("expires_in", 3000)))
    return _token["value"]

async def auth_headers() -> dict:
    if settings.azure_openai_auth == "entra": return {"Authorization": f"Bearer {await _entra_token()}"}
    return {"api-key": settings.azure_openai_api_key}

def _url(kind: str, deployment: str) -> str:
    return f"{_endpoint()}/openai/deployments/{deployment}/{kind}?api-version={settings.azure_openai_api_version}"

def _safe_error(resp: httpx.Response) -> str:
    try: code = (resp.json().get("error") or {}).get("code") or ""
    except Exception: code = ""
    return f"Azure OpenAI request failed ({resp.status_code}{', ' + str(code) if code else ''})"

async def chat_json(messages: list[dict], model: type[BaseModel], timeout: int = 60, retries: int = 2) -> BaseModel:
    """Call the chat deployment and return a validated pydantic object."""
    if not ai_configured(): raise AIUnavailable("The Microsoft AI service (Azure OpenAI) is not configured")
    schema = model.model_json_schema()
    body = {"messages": messages, "response_format": {"type": "json_schema", "json_schema": {"name": model.__name__, "schema": schema}}}
    if settings.azure_openai_use_temperature: body["temperature"] = 0
    url = _url("chat/completions", settings.azure_openai_chat_deployment)
    json_mode = False; last = "Azure OpenAI request failed"
    for attempt in range(retries + 2):
        headers = {**await auth_headers(), "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=timeout) as c: resp = await c.post(url, headers=headers, json=body)
        if resp.status_code in (429, 500, 502, 503, 504):
            last = _safe_error(resp); await asyncio.sleep(min(2 ** attempt, 8)); continue
        if resp.status_code == 400 and not json_mode and "response_format" in resp.text:
            # Older deployments without JSON-schema support: fall back to JSON mode with the schema in the prompt.
            json_mode = True
            body["response_format"] = {"type": "json_object"}
            body["messages"] = [*messages, {"role": "system", "content": "Respond only with one JSON object that matches this JSON schema: " + json.dumps(schema)}]
            continue
        if resp.status_code >= 400: raise AIUnavailable(_safe_error(resp))
        choice = (resp.json().get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content")
        if not content: last = "Azure OpenAI returned no content" + (f" ({choice.get('finish_reason')})" if choice.get("finish_reason") else ""); continue
        try: return model.model_validate_json(content)
        except ValidationError: last = "Azure OpenAI returned JSON that did not match the expected format"; continue
    raise AIUnavailable(last)

def to_messages(prompt, variables: dict) -> list[dict]:
    """Render a langchain ChatPromptTemplate into chat-completion messages."""
    role = {"system": "system", "human": "user", "ai": "assistant"}
    return [{"role": role.get(m.type, "user"), "content": m.content} for m in prompt.format_messages(**variables)]

async def transcribe(filename: str, data: bytes) -> dict:
    if not transcription_configured(): raise AIUnavailable("Audio transcription (Azure OpenAI Whisper deployment) is not configured")
    url = _url("audio/transcriptions", settings.azure_openai_transcription_deployment)
    async with httpx.AsyncClient(timeout=180) as c:
        resp = await c.post(url, headers=await auth_headers(), data={"response_format": "verbose_json", "timestamp_granularities[]": "segment"}, files={"file": (filename, data, "application/octet-stream")})
    if resp.status_code == 429: raise AIUnavailable("Audio transcription was throttled")
    if resp.status_code >= 400: raise AIUnavailable(_safe_error(resp).replace("request", "transcription"))
    return resp.json()

async def ping() -> tuple[bool, str]:
    """Tiny real request used by the Admin 'Test connections' button."""
    if not ai_configured(): return False, "Not configured"
    try:
        body = {"messages": [{"role": "user", "content": "Reply with OK."}], "max_completion_tokens": 8}
        async with httpx.AsyncClient(timeout=20) as c:
            resp = await c.post(_url("chat/completions", settings.azure_openai_chat_deployment), headers={**await auth_headers(), "Content-Type": "application/json"}, json=body)
        if resp.status_code < 400: return True, "Chat deployment responded."
        return False, _safe_error(resp)
    except AIUnavailable as exc: return False, str(exc)
    except Exception: return False, "The service could not be reached."

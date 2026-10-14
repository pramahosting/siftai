from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
import time
import jwt
import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)
_jwks_cache: tuple[float, dict] | None = None

async def _jwks() -> dict:
    global _jwks_cache
    if _jwks_cache and _jwks_cache[0] > time.time(): return _jwks_cache[1]
    if not settings.entra_tenant_id: raise HTTPException(503, "Microsoft Entra authentication is not configured")
    url = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/discovery/v2.0/keys"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url); response.raise_for_status(); data = response.json()
    _jwks_cache = (time.time() + 3600, data)
    return data

async def principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: AsyncSession = Depends(get_db)) -> User:
    if not credentials: raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate":"Bearer"})
    token = credentials.credentials
    if settings.is_local_demo:
        try: claims = jwt.decode(token, settings.local_auth_secret, algorithms=["HS256"], audience="meeting-intelligence-api")
        except jwt.PyJWTError: raise HTTPException(401, "Invalid development session")
    else:
        try:
            hdr = jwt.get_unverified_header(token); keys = await _jwks(); jwk = next(k for k in keys["keys"] if k["kid"] == hdr.get("kid"))
            signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
            claims = jwt.decode(token, signing_key, algorithms=["RS256"], audience=settings.entra_api_audience,
                                issuer=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
                                options={"require":["exp","iss","aud"]})
        except Exception as exc: raise HTTPException(401, "Invalid Microsoft Entra access token") from exc
    subject = claims.get("oid") or claims.get("sub")
    email = (claims.get("preferred_username") or claims.get("email") or "").lower()
    if not subject or not email: raise HTTPException(401, "Token is missing a stable user identity")
    role_names = claims.get("roles", [])
    is_local_admin = settings.is_local_demo and email == "admin@example.test"
    claim_admin = is_local_admin or settings.entra_admin_role in role_names or email in settings.admins
    result = await db.execute(select(User).where(User.entra_subject == subject))
    user = result.scalar_one_or_none()
    if not user:
        user = User(entra_subject=subject, email=email, display_name=claims.get("name", email), role="admin" if claim_admin else "user")
        db.add(user)
    else:
        user.email=email; user.display_name=user.display_name or claims.get("name", email)
        # An administrator's choice (Users page) applies; sign-in claims and ADMIN_EMAILS can only add admin rights.
        user.role = "admin" if claim_admin or user.role_override == "admin" else "user"
    if user.is_active is False: raise HTTPException(403, "This account is disabled. Contact an administrator.")
    now = datetime.now(timezone.utc)
    if not user.last_login_at or (now - (user.last_login_at if user.last_login_at.tzinfo else user.last_login_at.replace(tzinfo=timezone.utc))).total_seconds() > 300:
        user.last_login_at = now
    try:
        await db.commit()
    except IntegrityError:
        # Two requests from the same new user arrived together; the other one created the row first.
        await db.rollback()
        user = (await db.execute(select(User).where(User.entra_subject == subject))).scalar_one()
    await db.refresh(user)
    return user

def require_admin(user: User = Depends(principal)) -> User:
    if user.role != "admin": raise HTTPException(403, "Administrator role required")
    return user


import hashlib, hmac, os as _os
def hash_password(password: str) -> str:
    salt = _os.urandom(16); iters = 200_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters)
    return f"pbkdf2_sha256${iters}${salt.hex()}${digest.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(check.hex(), digest)
    except Exception:
        return False

import hashlib
import os
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import ApiToken, User, get_db

# Security
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY environment variable must be set! "
        "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def _touch_last_active(db: Session, user: User) -> None:
    """Record activity for the lifecycle sweep — throttled.

    The sweep works in days, so minute precision is plenty. Committing on
    every request turned each authed GET into a SQLite write, which under
    two uvicorn workers is the classic "database is locked" recipe.
    """
    now = datetime.utcnow()
    stale = user.last_active is None or (now - user.last_active) > timedelta(minutes=5)
    dormant = user.account_status == "dormant"
    if stale or dormant:
        user.last_active = now
        # A dormant user showing up again is reactivated on any authed
        # request, so the sweep never deletes an account that has been
        # active since its warning.
        if dormant:
            user.account_status = "active"
        db.commit()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)
) -> User | None:
    if not credentials:
        return None

    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        return None

    username = payload.get("sub")
    if not username:
        return None

    user = db.query(User).filter(User.username == username).first()
    if user:
        _touch_last_active(db, user)

    return user


async def require_auth(user: User = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def require_admin(user: User = Depends(require_auth)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# --- Personal access tokens (Phase #121 — external integrations) ---------
#
# A second, narrower auth mechanism alongside the JWT session above: a
# long-lived, user-issued, scope-limited token for outside apps (e.g. a
# speaking-companion's own whisper/LLM/TTS stack) that only needs to read
# and report vocabulary state, never the full account. See
# app/routers/tokens.py (issuing) and app/routers/external.py (the
# endpoints these tokens actually unlock).

API_TOKEN_PREFIX = "qd_"
API_TOKEN_SCOPES = frozenset({"read:words", "write:words"})


def generate_api_token() -> str:
    return API_TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_api_token(token: str) -> str:
    # Unlike passwords, these are already high-entropy random strings, so a
    # fast cryptographic hash (not bcrypt) is the right tool — same
    # approach GitHub/Stripe use for their PATs.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_api_scope(scope: str):
    """Dependency factory for the external API. Accepts either:

    - a normal JWT session — a logged-in browser already has full access,
      so no scope check applies; or
    - a personal access token that carries `scope` in its scope list.

    Kept separate from get_current_user/require_auth so the SPA's own
    routes are never reachable with a narrowly-scoped PAT by accident.
    """

    async def _dep(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db),
    ) -> User:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )
        token = credentials.credentials

        payload = decode_token(token)
        if payload:
            username = payload.get("sub")
            user = db.query(User).filter(User.username == username).first() if username else None
            if user:
                _touch_last_active(db, user)
                return user

        row = (
            db.query(ApiToken)
            .filter(ApiToken.token_hash == hash_api_token(token), ApiToken.revoked_at.is_(None))
            .first()
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )
        if scope not in (row.scopes or "").split():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Token missing required scope: {scope}",
            )
        row.last_used_at = datetime.utcnow()
        db.commit()
        return row.user

    return _dep


async def get_user_from_token_or_query(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User | None:
    """
    Get user from Authorization header OR from query parameter token.
    Used for downloads where we can't set custom headers in iframe/form submissions.
    """
    token = None

    # Try to get token from Authorization header first
    if credentials:
        token = credentials.credentials
    # Fallback to query parameter (for iframe downloads)
    elif "token" in request.query_params:
        token = request.query_params["token"]

    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    username = payload.get("sub")
    if not username:
        return None

    user = db.query(User).filter(User.username == username).first()
    if user:
        _touch_last_active(db, user)

    return user


async def require_auth_flexible(user: User = Depends(get_user_from_token_or_query)) -> User:
    """
    Require authentication from either header or query parameter.
    Used for download endpoints that need to work with iframe submissions.
    """
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user

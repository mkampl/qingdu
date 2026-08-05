"""
Personal access tokens for external integrations — e.g. a speech/LLM
companion app that wants to read a user's known-word set and report newly
encountered vocabulary back into qingdu. See app/routers/external.py for
the endpoints these tokens actually unlock.

Token management itself is JWT-session-only (require_auth): a leaked PAT
must never be able to mint more tokens or revoke the others.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import API_TOKEN_SCOPES, generate_api_token, hash_api_token, require_auth
from app.database import ApiToken, User, get_db

router = APIRouter(prefix="/api/tokens", tags=["API Tokens"])


class CreateTokenRequest(BaseModel):
    name: str
    scopes: list[str]


@router.get("")
async def list_tokens(user: User = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    rows = (
        db.query(ApiToken)
        .filter(ApiToken.user_id == user.id, ApiToken.revoked_at.is_(None))
        .order_by(ApiToken.created_at.desc())
        .all()
    )
    return {
        "tokens": [
            {
                "id": row.id,
                "name": row.name,
                "token_prefix": row.token_prefix,
                "scopes": row.scopes.split(),
                "created_at": row.created_at,
                "last_used_at": row.last_used_at,
            }
            for row in rows
        ]
    }


@router.post("")
async def create_token(
    payload: CreateTokenRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    scopes = {s.strip() for s in payload.scopes if s.strip()}
    if not scopes:
        raise HTTPException(status_code=400, detail="At least one scope is required")
    invalid = scopes - API_TOKEN_SCOPES
    if invalid:
        raise HTTPException(
            status_code=400, detail=f"Unknown scope(s): {', '.join(sorted(invalid))}"
        )

    raw_token = generate_api_token()
    row = ApiToken(
        user_id=user.id,
        name=name,
        token_hash=hash_api_token(raw_token),
        token_prefix=raw_token[:10],
        scopes=" ".join(sorted(scopes)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "id": row.id,
        "name": row.name,
        # Shown once — the hash above is all that's kept from here on.
        "token": raw_token,
        "token_prefix": row.token_prefix,
        "scopes": row.scopes.split(),
        "created_at": row.created_at,
    }


@router.delete("/{token_id}")
async def revoke_token(
    token_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    row = db.query(ApiToken).filter(ApiToken.id == token_id, ApiToken.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Token not found")
    row.revoked_at = datetime.utcnow()
    db.commit()
    return {"revoked": True}

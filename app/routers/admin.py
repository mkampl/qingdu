import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import (
    bump_token_version,
    get_password_hash,
    require_admin,
    validate_new_credentials,
)
from app.core.constants import API_TIMEOUT, MIN_PASSWORD_LENGTH
from app.database import User, get_db
from app.schemas import (
    CreateUserRequest,
    RegistrationSettingsUpdate,
    UpdateInviteQuotaRequest,
)
from app.services import lifecycle
from app.services.timestamps import iso_utc

router = APIRouter(tags=["Admin"])


@router.get("/api/admin/registration-settings")
async def get_registration_settings(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """The instance-wide registration and lifecycle settings."""
    return lifecycle.get_settings(db)


@router.patch("/api/admin/registration-settings")
async def update_registration_settings(
    data: RegistrationSettingsUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Partial update of the registration and lifecycle settings."""
    mapping = {
        "registration_open": "registration.open",
        "registration_per_ip_24h": "registration.per_ip_24h",
        "registration_daily_cap": "registration.daily_cap",
        "registration_captcha": "registration.captcha",
        "lifecycle_soft_delete_days": "lifecycle.soft_delete_days",
        "lifecycle_hard_delete_days": "lifecycle.hard_delete_days",
    }
    updates: dict[str, object] = {}
    payload = data.model_dump(exclude_none=True)
    for field, key in mapping.items():
        if field in payload:
            updates[key] = payload[field]
    # Sanity: hard_delete_days must be >= soft_delete_days when both > 0.
    soft = (
        updates.get("lifecycle.soft_delete_days")
        if "lifecycle.soft_delete_days" in updates
        else lifecycle.get_setting(db, "lifecycle.soft_delete_days")
    )
    hard = (
        updates.get("lifecycle.hard_delete_days")
        if "lifecycle.hard_delete_days" in updates
        else lifecycle.get_setting(db, "lifecycle.hard_delete_days")
    )
    if soft and hard and int(hard) < int(soft):
        raise HTTPException(
            status_code=400,
            detail="Hard-delete threshold must be at least the soft-delete threshold.",
        )
    return lifecycle.set_settings(db, updates)


@router.post("/api/admin/lifecycle/run-now")
async def run_lifecycle_now(
    admin: User = Depends(require_admin),
):
    """Run a lifecycle sweep now instead of waiting for the scheduled one."""
    return lifecycle.run_lifecycle_pass()


@router.get("/api/admin/users")
async def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "is_admin": u.is_admin,
            "invite_quota": u.invite_quota,
            "last_active": iso_utc(u.last_active),
            "created_at": iso_utc(u.created_at),
        }
        for u in users
    ]


@router.post("/api/admin/users")
async def create_user(
    data: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        username = validate_new_credentials(data.username, data.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )
    user = User(
        username=username,
        password_hash=get_password_hash(data.password),
        is_admin=False,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    return {"message": f"User {username} created successfully"}


@router.delete("/api/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete admin users"
        )
    username = user.username
    lifecycle.purge_user(db, user)
    db.commit()
    return {"message": f"User {username} deleted"}


@router.post("/api/admin/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    data: dict,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    new_password = data.get("new_password")
    if not new_password or len(new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )
    user.password_hash = get_password_hash(new_password)
    user.must_change_password = True
    # Sign the user out everywhere — the reset usually means the old
    # password (and whoever held it) should lose access.
    bump_token_version(user)
    db.commit()
    return {"message": f"Password reset for {user.username}"}


@router.post("/api/admin/users/{user_id}/toggle-admin")
async def toggle_admin_status(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot change your own admin status")
    user.is_admin = not user.is_admin
    db.commit()
    return {"message": f"User is now {'admin' if user.is_admin else 'regular user'}"}


@router.patch("/api/admin/users/{user_id}/invite-quota")
async def update_user_invite_quota(
    user_id: int,
    data: UpdateInviteQuotaRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a user's invitation quota (admin only). -1 = unlimited."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.invite_quota < -1:
        raise HTTPException(
            status_code=400,
            detail="Quota cannot be less than -1 (use -1 for unlimited)",
        )
    user.invite_quota = data.invite_quota
    db.commit()
    return {
        "message": "Invite quota updated",
        "user_id": user.id,
        "username": user.username,
        "invite_quota": user.invite_quota,
    }


# --- Translation-provider healthcheck ----------------------------------------
#
# Probes each provider with a known phrase so an admin can confirm DeepL,
# Google and MyMemory are reachable and accept the auth we send. The
# translation chain falls through silently, so a bad key or an API change
# shows up here first.

_PROBE_TEXT = "你好"


async def _probe(send, translation_of) -> dict:
    """Run one provider request; `translation_of` reads the JSON reply."""
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            response = await send(client)
        if response.is_success:
            translation = translation_of(response.json())
            return {"status": "ok", "http_status": response.status_code, "translation": translation}
        return {
            "status": "error",
            "http_status": response.status_code,
            "detail": response.text[:300],
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)[:300]}


async def _probe_deepl() -> dict:
    key = os.getenv("DEEPL_API_KEY")
    if not key:
        return {"status": "not_configured", "detail": "DEEPL_API_KEY is empty"}
    return await _probe(
        lambda client: client.post(
            "https://api-free.deepl.com/v2/translate",
            headers={"Authorization": f"DeepL-Auth-Key {key}"},
            data={"text": _PROBE_TEXT, "target_lang": "EN", "source_lang": "ZH"},
        ),
        lambda data: (data.get("translations") or [{}])[0].get("text", ""),
    )


async def _probe_google() -> dict:
    key = os.getenv("GOOGLE_TRANSLATE_API_KEY")
    if not key:
        return {"status": "not_configured", "detail": "GOOGLE_TRANSLATE_API_KEY is empty"}
    return await _probe(
        lambda client: client.post(
            "https://translation.googleapis.com/language/translate/v2",
            params={"key": key, "q": _PROBE_TEXT, "target": "en", "source": "zh"},
        ),
        lambda data: ((data.get("data") or {}).get("translations") or [{}])[0].get(
            "translatedText", ""
        ),
    )


async def _probe_mymemory() -> dict:
    return await _probe(
        lambda client: client.get(
            f"https://api.mymemory.translated.net/get?q={_PROBE_TEXT}&langpair=zh|en"
        ),
        lambda data: (data.get("responseData") or {}).get("translatedText", ""),
    )


@router.get("/api/admin/translate-providers")
async def translate_providers_healthcheck(
    admin: User = Depends(require_admin),
):
    """Probe each translation provider (DeepL, Google, MyMemory) with the
    same Chinese phrase and report which ones work."""
    _ = admin
    deepl, google, mymemory = (
        await _probe_deepl(),
        await _probe_google(),
        await _probe_mymemory(),
    )
    return {
        "probe": _PROBE_TEXT,
        "providers": {
            "deepl": deepl,
            "google": google,
            "mymemory": mymemory,
        },
    }

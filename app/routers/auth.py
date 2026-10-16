from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import (
    DOWNLOAD_PATHS,
    bump_token_version,
    create_download_ticket,
    create_session_token,
    get_current_user,
    get_password_hash,
    require_auth,
    require_auth_flexible,
    validate_new_credentials,
    verify_password,
)
from app.core.constants import AUTH_RATE_LIMIT, MIN_PASSWORD_LENGTH
from app.core.rate_limit import client_ip, limiter
from app.database import (
    InvitationToken,
    SavedText,
    User,
    UserWord,
    UserWordEvent,
    VocabularyList,
    get_db,
)
from app.schemas import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    LoginRequest,
    OpenRegisterRequest,
    SignupWithInviteRequest,
    UserSettingsUpdate,
)
from app.services import captcha, lifecycle, localday, srs, streak
from app.services.timestamps import iso_utc

router = APIRouter(tags=["Authentication"])


# Same derivation as the rate limiter, so signup caps and slowapi agree on
# who the client is.
_client_ip = client_ip


@router.post(
    "/api/auth/login",
    summary="User login",
    description=(
        "Authenticate user and receive JWT access token. The admin password "
        "is generated at first startup and written to data/admin_bootstrap.txt."
    ),
    response_description="JWT token and user information",
    responses={
        200: {
            "description": "Successful login",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                        "user": {
                            "username": "admin",
                            "is_admin": True,
                            "must_change_password": False,
                        },
                    }
                }
            },
        },
        401: {"description": "Invalid username or password"},
        429: {"description": "Rate limit exceeded (5 requests/minute)"},
    },
)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    access_token = create_session_token(user)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": user.username,
            "is_admin": user.is_admin,
            "must_change_password": user.must_change_password,
        },
    }


@router.get("/api/auth/me")
async def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return {"authenticated": False}
    # Phase 2.7 — lifecycle expiry. Computed from the live settings every
    # call so the SPA can show countdowns / schedule local notifications
    # without a separate fetch. Admin accounts always get None back.
    settings = lifecycle.get_settings(db)
    expiry = lifecycle.expiry_for(user, settings)
    return {
        "authenticated": True,
        "user": {
            "username": user.username,
            "is_admin": user.is_admin,
            "must_change_password": user.must_change_password,
            # Phase #96 — settings exposed alongside identity so the SPA's
            # SettingsModal can read + edit them without a second round-trip.
            # daily_new_words default is 0 (off) — users opt in from Settings.
            "daily_new_words": user.daily_new_words if user.daily_new_words is not None else 0,
            "hsk_focus_version": user.hsk_focus_version or "new",
            "display_script": user.display_script or "auto",
            "review_retention": (
                user.review_retention if user.review_retention is not None else 0.95
            ),
            "review_window": user.review_window or "today",
            "review_focus": user.review_focus or "both",
            # IANA zone for local-day boundaries; null until the SPA sends
            # the browser's zone on first load.
            "timezone": user.timezone,
            "account_status": user.account_status or "active",
            "soft_delete_at": iso_utc(expiry["soft_delete_at"]),
            "hard_delete_at": iso_utc(expiry["hard_delete_at"]),
        },
    }


@router.get(
    "/api/auth/captcha",
    summary="Issue a math captcha for open registration",
)
@limiter.limit("30/minute")
async def issue_captcha(request: Request):
    """Stateless math captcha. Reply carries the question (e.g. '5 + 7') and
    a short-lived JWT the client returns with `POST /api/auth/register`."""
    return captcha.issue()


@router.get(
    "/api/auth/registration-status",
    summary="Whether open registration is currently accepting new users",
)
async def registration_status(db: Session = Depends(get_db)):
    """Public — used by the SPA to decide whether to render the Sign Up
    link in the login modal. Returns the captcha flag so the form can
    skip the captcha entirely when the instance disables it."""
    settings = lifecycle.get_settings(db)
    return {
        "open": bool(settings.get("registration.open")),
        "captcha": bool(settings.get("registration.captcha")),
    }


@router.post(
    "/api/auth/register",
    summary="Open registration (when enabled by the admin)",
)
@limiter.limit("10/minute")
async def open_register(
    request: Request,
    data: OpenRegisterRequest,
    db: Session = Depends(get_db),
):
    """Self-service signup. Subject to the instance settings:
    `registration.open` must be on, captcha must validate (if enabled),
    per-IP and global daily caps are enforced.

    The `honeypot` field is accepted for back-compat with v1.0.45 clients
    but is NOT checked — Android autofill / password managers cheerfully
    fill sr-only fields, which trapped legitimate signup attempts on
    mobile. Captcha + IP rate limit + global daily cap are enough for a
    demo this size."""
    ip = _client_ip(request)
    settings = lifecycle.get_settings(db)
    try:
        lifecycle.check_signup_allowed(db, ip)
    except lifecycle.SignupBlocked as exc:
        lifecycle.record_attempt(db, ip, successful=False)
        status_code = 403 if exc.code == "closed" else 429
        raise HTTPException(status_code=status_code, detail=exc.detail) from exc

    if bool(settings.get("registration.captcha")) and not captcha.verify(
        data.captcha_token or "", data.captcha_answer
    ):
        lifecycle.record_attempt(db, ip, successful=False)
        raise HTTPException(
            status_code=400,
            detail="Captcha answer is incorrect or expired. Try again.",
        )

    try:
        username = validate_new_credentials(data.username, data.password)
    except ValueError as exc:
        lifecycle.record_attempt(db, ip, successful=False)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if db.query(User).filter(User.username == username).first():
        lifecycle.record_attempt(db, ip, successful=False)
        raise HTTPException(status_code=400, detail="Username already taken.")

    new_user = User(
        username=username,
        password_hash=get_password_hash(data.password),
        must_change_password=False,
        invite_quota=0,  # no invite quota until the admin grants one
    )
    db.add(new_user)
    db.flush()
    lifecycle.record_attempt(db, ip, successful=True)
    db.commit()

    token = create_session_token(new_user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "is_admin": new_user.is_admin,
        },
    }


@router.patch("/api/auth/me/settings")
async def update_my_settings(
    payload: UserSettingsUpdate,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Update the current user's tunable settings. Partial — fields left
    unset on the request are left untouched on the user."""
    if payload.daily_new_words is not None and not 0 <= payload.daily_new_words <= 30:
        raise HTTPException(status_code=400, detail="daily_new_words must be between 0 and 30")
    if payload.hsk_focus_version is not None and payload.hsk_focus_version not in {"new", "old"}:
        raise HTTPException(status_code=400, detail="hsk_focus_version must be 'new' or 'old'")
    if payload.display_script is not None and payload.display_script not in {
        "auto",
        "simp",
        "trad",
    }:
        raise HTTPException(
            status_code=400,
            detail="display_script must be 'auto', 'simp', or 'trad'",
        )
    if payload.review_retention is not None and not 0.85 <= payload.review_retention <= 0.97:
        raise HTTPException(
            status_code=400,
            detail="review_retention must be between 0.85 and 0.97",
        )
    if payload.review_window is not None and payload.review_window not in {
        "now",
        "today",
        "tomorrow",
    }:
        raise HTTPException(
            status_code=400,
            detail="review_window must be 'now', 'today', or 'tomorrow'",
        )
    if payload.review_focus is not None and payload.review_focus not in srs.REVIEW_FOCUSES:
        raise HTTPException(
            status_code=400,
            detail="review_focus must be 'both', 'reading', or 'writing'",
        )
    if payload.timezone is not None and not localday.is_valid_timezone(payload.timezone):
        raise HTTPException(status_code=400, detail="timezone must be a known IANA zone name")
    user = db.merge(user)
    if payload.daily_new_words is not None:
        user.daily_new_words = payload.daily_new_words
    if payload.hsk_focus_version is not None:
        user.hsk_focus_version = payload.hsk_focus_version
    if payload.display_script is not None:
        user.display_script = payload.display_script
    if payload.review_retention is not None:
        user.review_retention = payload.review_retention
    if payload.review_window is not None:
        user.review_window = payload.review_window
    if payload.review_focus is not None:
        user.review_focus = payload.review_focus
    if payload.timezone is not None and payload.timezone != user.timezone:
        # Day boundaries move with the zone; keep the streak whole across it.
        streak.rebase_for_timezone(
            user, localday.user_tz(user), localday.resolve_tz(payload.timezone)
        )
        user.timezone = payload.timezone
    db.commit()
    return {
        "daily_new_words": user.daily_new_words,
        "hsk_focus_version": user.hsk_focus_version,
        "display_script": user.display_script,
        "review_retention": user.review_retention,
        "review_window": user.review_window,
        "review_focus": user.review_focus,
        "timezone": user.timezone,
    }


@router.post("/api/auth/logout")
async def logout():
    """Client-side token removal — server-side this is a no-op."""
    return {"message": "Logged out successfully"}


class DownloadTicketRequest(BaseModel):
    path: str = Field(..., max_length=200)


@router.post("/api/auth/download-ticket")
async def download_ticket(payload: DownloadTicketRequest, user: User = Depends(require_auth)):
    """A short-lived ticket that opens one download as a plain link
    (`<path>?ticket=…`), so the session token never lands in a URL."""
    if not DOWNLOAD_PATHS.match(payload.path):
        raise HTTPException(status_code=400, detail="Not a download")
    return {"ticket": create_download_ticket(user, payload.path)}


@router.get("/api/auth/export")
async def export_my_data(
    user: User = Depends(require_auth_flexible),
    db: Session = Depends(get_db),
):
    """Everything the server knows about this account, as one JSON file.

    The escape hatch the demo's inactivity deletion policy owes its users
    (and what the F-Droid crowd rightly expects): texts, word states with
    their FSRS scheduling, glosses, vocab lists, the review event log, and
    profile settings. `analysis_data` is deliberately excluded — it is a
    derived cache, re-created by pasting the text back in, and it dwarfs
    everything else combined. Flexible auth so a plain <a download> works.
    """
    from fastapi.responses import JSONResponse

    words = db.query(UserWord).filter(UserWord.user_id == user.id).all()
    payload = {
        "format": "qingdu-export",
        "version": 1,
        "exported_at": iso_utc(datetime.utcnow()),
        "profile": {
            "username": user.username,
            "created_at": iso_utc(user.created_at),
            "settings": {
                "daily_new_words": user.daily_new_words,
                "hsk_focus_version": user.hsk_focus_version,
                "display_script": user.display_script,
                "review_retention": user.review_retention,
                "review_window": user.review_window,
                "review_focus": user.review_focus,
                "timezone": user.timezone,
            },
        },
        "texts": [
            {
                "title": t.title,
                "content": t.content,
                "tags": t.tags,
                "reading_progress": t.reading_progress,
                "created_at": iso_utc(t.created_at),
            }
            for t in db.query(SavedText).filter(SavedText.user_id == user.id).all()
        ],
        "vocabulary_lists": [
            {
                "name": vl.name,
                "list_type": vl.list_type,
                "sections": vl.sections,
                "apply_as_glossary": vl.apply_as_glossary,
                "created_at": iso_utc(vl.created_at),
            }
            for vl in db.query(VocabularyList).filter(VocabularyList.user_id == user.id).all()
        ],
        "words": [
            {
                "word": w.word,
                "state": w.state,
                "seen_count": w.seen_count,
                "pinyin": w.pinyin,
                "meaning": w.meaning,
                "ease": w.ease,
                "stability": w.stability,
                "difficulty": w.difficulty,
                "due_at": iso_utc(w.due_at),
                "last_reviewed_at": iso_utc(w.last_reviewed_at),
                "glosses": [
                    {
                        "meaning": g.meaning,
                        "pinyin": g.pinyin,
                        "source": g.source,
                        "source_tag": g.source_tag,
                    }
                    for g in w.glosses
                ],
            }
            for w in words
        ],
        "review_events": [
            {
                "word": e.word,
                "event_type": e.event_type,
                "new_state": e.new_state,
                "grade": e.grade,
                "mode": e.mode,
                "created_at": iso_utc(e.created_at),
            }
            for e in db.query(UserWordEvent)
            .filter(UserWordEvent.user_id == user.id)
            .order_by(UserWordEvent.created_at)
            .all()
        ],
    }
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="qingdu-{user.username}.json"'},
    )


@router.delete("/api/auth/me")
async def delete_my_account(
    data: DeleteAccountRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Self-service account deletion — immediate and irreversible.

    Password re-entry guards against a left-open session. A wrong password
    is 403, not 401: the session itself is fine, and the SPA treats 401 as
    "logged out". Admins must
    demote themselves first (or use another admin), mirroring the
    admin-panel rule, so an instance can't delete its last admin by
    accident.
    """
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password is incorrect")
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts can't self-delete. Demote this account first.",
        )
    lifecycle.purge_user(db, user)
    db.commit()
    return {"message": "Account and all associated data deleted."}


@router.post("/api/auth/change-password")
async def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Change the caller's password. Every other session of this account is
    signed out (token_version bump); the caller gets a fresh token back.
    A wrong old password is 403 (not 401) so the SPA keeps the session."""
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid old password")
    if len(data.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )
    user = db.merge(user)
    user.password_hash = get_password_hash(data.new_password)
    user.must_change_password = False
    bump_token_version(user)
    db.commit()
    return {
        "message": "Password changed successfully",
        "access_token": create_session_token(user),
        "token_type": "bearer",
    }


@router.post("/api/auth/signup-with-invite")
async def signup_with_invite(
    data: SignupWithInviteRequest,
    db: Session = Depends(get_db),
):
    """Register a new user with an invitation token."""
    invitation = db.query(InvitationToken).filter(InvitationToken.token == data.token).first()
    if not invitation:
        raise HTTPException(status_code=400, detail="Invalid invitation token")
    if invitation.claimed_at:
        raise HTTPException(status_code=400, detail="Invitation already used")
    if invitation.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invitation expired")

    try:
        username = validate_new_credentials(data.username, data.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    new_user = User(
        username=username,
        password_hash=get_password_hash(data.password),
        must_change_password=False,
        invite_quota=5,
    )
    db.add(new_user)
    db.flush()

    invitation.claimed_by_user_id = new_user.id
    invitation.claimed_at = datetime.utcnow()
    db.commit()

    token = create_session_token(new_user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "is_admin": new_user.is_admin,
        },
    }

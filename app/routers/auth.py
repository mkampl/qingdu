from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    get_current_user,
    get_password_hash,
    require_auth,
    verify_password,
)
from app.core.constants import AUTH_RATE_LIMIT, MIN_PASSWORD_LENGTH
from app.core.rate_limit import limiter
from app.database import InvitationToken, User, get_db
from app.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    SignupWithInviteRequest,
    UserSettingsUpdate,
)

router = APIRouter(tags=["Authentication"])


@router.post(
    "/api/auth/login",
    summary="User login",
    description=(
        "Authenticate user and receive JWT access token. Default credentials: "
        "admin/admin123 (must be changed on first login)."
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

    access_token = create_access_token(data={"sub": user.username})
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
async def get_me(user: User = Depends(get_current_user)):
    if not user:
        return {"authenticated": False}
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
    user = db.merge(user)
    if payload.daily_new_words is not None:
        user.daily_new_words = payload.daily_new_words
    if payload.hsk_focus_version is not None:
        user.hsk_focus_version = payload.hsk_focus_version
    db.commit()
    return {
        "daily_new_words": user.daily_new_words,
        "hsk_focus_version": user.hsk_focus_version,
    }


@router.post("/api/auth/logout")
async def logout():
    """Client-side token removal — server-side this is a no-op."""
    return {"message": "Logged out successfully"}


@router.post("/api/auth/change-password")
async def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid old password")
    if len(data.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )
    user.password_hash = get_password_hash(data.new_password)
    user.must_change_password = False
    db.commit()
    return {"message": "Password changed successfully"}


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

    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    new_user = User(
        username=data.username,
        password_hash=get_password_hash(data.password),
        must_change_password=False,
        invite_quota=5,
    )
    db.add(new_user)
    db.flush()

    invitation.claimed_by_user_id = new_user.id
    invitation.claimed_at = datetime.utcnow()
    db.commit()

    token = create_access_token(data={"sub": new_user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "is_admin": new_user.is_admin,
        },
    }

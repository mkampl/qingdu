import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import InvitationToken, User, get_db

router = APIRouter(tags=["Invitations"])


@router.post("/api/invitations/generate")
async def generate_invitation(
    request: Request,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Generate a new invitation token (skips quota check if quota is -1)."""
    used_count = (
        db.query(InvitationToken).filter(InvitationToken.created_by_user_id == user.id).count()
    )

    if user.invite_quota >= 0 and used_count >= user.invite_quota:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail=(
                f"Invitation quota exceeded. You have used "
                f"{used_count}/{user.invite_quota} invitations."
            ),
        )

    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=30)

    invitation = InvitationToken(token=token, created_by_user_id=user.id, expires_at=expires_at)
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    base_url = (
        str(request.url).split("/api")[0] if hasattr(request, "url") else "http://localhost:8000"
    )
    invite_url = f"{base_url}/?invite={token}"

    return {
        "id": invitation.id,
        "token": token,
        "invite_url": invite_url,
        "expires_at": invitation.expires_at.isoformat(),
        "remaining_quota": (-1 if user.invite_quota == -1 else user.invite_quota - used_count - 1),
    }


@router.get("/api/invitations/my-invitations")
async def get_my_invitations(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Return all invitations created by the current user, with quota summary."""
    invitations = (
        db.query(InvitationToken)
        .filter(InvitationToken.created_by_user_id == user.id)
        .order_by(InvitationToken.created_at.desc())
        .all()
    )
    used_count = len(invitations)

    def _status(inv: InvitationToken) -> str:
        if inv.claimed_at:
            return "claimed"
        if inv.expires_at < datetime.utcnow():
            return "expired"
        return "pending"

    # One IN query for all claimer names instead of one query per invitation.
    claimer_ids = {inv.claimed_by_user_id for inv in invitations if inv.claimed_by_user_id}
    claimer_names = (
        dict(db.query(User.id, User.username).filter(User.id.in_(claimer_ids)).all())
        if claimer_ids
        else {}
    )

    def _claimed_username(inv: InvitationToken) -> str | None:
        if not inv.claimed_by_user_id:
            return None
        return claimer_names.get(inv.claimed_by_user_id)

    return {
        "invitations": [
            {
                "id": inv.id,
                "token": inv.token[-8:],
                "full_token": inv.token,
                "status": _status(inv),
                "claimed_by": _claimed_username(inv),
                "claimed_at": inv.claimed_at.isoformat() if inv.claimed_at else None,
                "expires_at": inv.expires_at.isoformat(),
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invitations
        ],
        "quota": {
            "total": user.invite_quota,
            "used": used_count,
            "remaining": (-1 if user.invite_quota == -1 else user.invite_quota - used_count),
        },
    }


@router.get("/api/invitations/validate/{token}")
async def validate_invitation(token: str, db: Session = Depends(get_db)):
    """Public endpoint — checks if an invitation token is usable."""
    invitation = db.query(InvitationToken).filter(InvitationToken.token == token).first()
    if not invitation:
        return {"valid": False, "reason": "not_found"}
    if invitation.claimed_at:
        return {"valid": False, "reason": "already_used"}
    if invitation.expires_at < datetime.utcnow():
        return {"valid": False, "reason": "expired"}

    creator = db.query(User).filter(User.id == invitation.created_by_user_id).first()
    return {
        "valid": True,
        "invited_by": creator.username if creator else "Unknown",
        "expires_at": invitation.expires_at.isoformat(),
    }

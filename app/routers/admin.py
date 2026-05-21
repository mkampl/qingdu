from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_password_hash, require_admin
from app.core.constants import MIN_PASSWORD_LENGTH
from app.database import User, get_db
from app.schemas import CreateUserRequest, UpdateInviteQuotaRequest

router = APIRouter(tags=["Admin"])


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
            "last_active": u.last_active.isoformat(),
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.post("/api/admin/users")
async def create_user(
    data: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )
    user = User(
        username=data.username,
        password_hash=get_password_hash(data.password),
        is_admin=False,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    return {"message": f"User {data.username} created successfully"}


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
    db.delete(user)
    db.commit()
    return {"message": f"User {user.username} deleted"}


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

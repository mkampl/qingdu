"""
Phase 2.7 — Account lifecycle + registration settings.

The instance has a small admin-tunable config surface stored in
`system_settings` (DB-backed, no env-var dance). The defaults below are
the conservative ones we ship for self-hosters: open registration off,
no inactivity cleanup. The maintainer's demo at qingdu.itvoodoo.at
flips them on via the admin UI.

The lifecycle sweep (`run_lifecycle_pass`) is fired both at boot and on
a periodic asyncio task. It is idempotent — a row already at the right
status, or older than the hard threshold, is handled once and skipped
thereafter.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal, SignupAttempt, SystemSetting, User

logger = logging.getLogger(__name__)


# ---- settings ----------------------------------------------------------

# Conservative defaults. Self-hosters get a closed-registration instance
# with no lifecycle cleanup. The maintainer toggles them in the admin UI.
DEFAULTS: dict[str, Any] = {
    "registration.open": False,
    # Per-IP signup limit over the last 24 h. 3 is enough for the legitimate
    # "I locked myself out, made a fresh account" case without giving spam
    # bots an easy hole.
    "registration.per_ip_24h": 3,
    # Global daily cap. 0 means unlimited (the default — self-hosters who
    # know their audience usually don't need a cap at all).
    "registration.daily_cap": 0,
    # Math captcha gate. Cheap, no external script, F-Droid-clean.
    "registration.captcha": True,
    # Days of inactivity before account is flipped to `dormant` and the
    # warning banner / local notification fires. 0 disables.
    "lifecycle.soft_delete_days": 0,
    # Days of inactivity before the account is hard-deleted. 0 disables.
    # Must be > soft_delete_days when both are set.
    "lifecycle.hard_delete_days": 0,
}


def _coerce(key: str, raw: str) -> Any:
    """Best-effort cast back to the type of the default."""
    default = DEFAULTS.get(key)
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
    if default is None:
        return loaded
    if isinstance(default, bool):
        return bool(loaded)
    if isinstance(default, int):
        try:
            return int(loaded)
        except (ValueError, TypeError):
            return default
    return loaded


def get_setting(db: Session, key: str) -> Any:
    """Read a single setting. Falls back to the DEFAULTS map."""
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        return DEFAULTS.get(key)
    return _coerce(key, row.value)


def get_settings(db: Session) -> dict[str, Any]:
    """Read every key. Missing rows default to the conservative shipped value."""
    rows = {r.key: _coerce(r.key, r.value) for r in db.query(SystemSetting).all()}
    return {k: rows.get(k, v) for k, v in DEFAULTS.items()}


def set_settings(db: Session, updates: dict[str, Any]) -> dict[str, Any]:
    """Upsert a set of settings. Unknown keys are ignored (not allow-listed)."""
    for key, value in updates.items():
        if key not in DEFAULTS:
            continue
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        encoded = json.dumps(value)
        if row:
            row.value = encoded
            row.updated_at = datetime.utcnow()
        else:
            db.add(SystemSetting(key=key, value=encoded))
    db.commit()
    return get_settings(db)


# ---- per-account lifecycle stamps -------------------------------------


def expiry_for(user: User, settings: dict[str, Any]) -> dict[str, datetime | None]:
    """Return the {soft_delete_at, hard_delete_at} stamps for a user, given
    the current instance settings. Returns None for disabled thresholds, and
    for staff (admins are never auto-deleted)."""
    if user.is_admin:
        return {"soft_delete_at": None, "hard_delete_at": None}
    last = user.last_active or user.created_at or datetime.utcnow()
    soft_days = int(settings.get("lifecycle.soft_delete_days") or 0)
    hard_days = int(settings.get("lifecycle.hard_delete_days") or 0)
    return {
        "soft_delete_at": (last + timedelta(days=soft_days)) if soft_days else None,
        "hard_delete_at": (last + timedelta(days=hard_days)) if hard_days else None,
    }


# ---- signup gate ------------------------------------------------------


class SignupBlocked(Exception):
    """Raised by `check_signup_allowed`. The router turns it into a 4xx."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(detail)


def check_signup_allowed(db: Session, ip_address: str) -> None:
    """Run the three gates: feature flag, per-IP, global daily cap.
    Raises SignupBlocked with a code the router maps to a 4xx + message."""
    settings = get_settings(db)
    if not settings.get("registration.open"):
        raise SignupBlocked("closed", "Open registration is disabled on this instance.")

    cutoff = datetime.utcnow() - timedelta(hours=24)
    per_ip_limit = int(settings.get("registration.per_ip_24h") or 0)
    if per_ip_limit > 0:
        ip_attempts = (
            db.query(SignupAttempt)
            .filter(SignupAttempt.ip_address == ip_address)
            .filter(SignupAttempt.created_at >= cutoff)
            .count()
        )
        if ip_attempts >= per_ip_limit:
            raise SignupBlocked(
                "ip_rate_limited",
                f"This network has reached the signup limit ({per_ip_limit} per 24 h).",
            )

    daily_cap = int(settings.get("registration.daily_cap") or 0)
    if daily_cap > 0:
        global_success = (
            db.query(SignupAttempt)
            .filter(SignupAttempt.created_at >= cutoff)
            .filter(SignupAttempt.successful.is_(True))
            .count()
        )
        if global_success >= daily_cap:
            raise SignupBlocked(
                "daily_cap_reached",
                "Today's signup cap has been reached. Please try again tomorrow.",
            )


def record_attempt(db: Session, ip_address: str, *, successful: bool) -> None:
    """Log a signup attempt for IP rate limiting + audit."""
    db.add(SignupAttempt(ip_address=ip_address, successful=successful))
    db.commit()


# ---- the lifecycle pass ----------------------------------------------


def run_lifecycle_pass(db: Session | None = None) -> dict[str, int]:
    """Mark dormant + hard-delete users that have crossed the thresholds.

    Returns a small stat dict the caller can log. Admins are never touched.
    Closing pruning of signup_attempts older than 24 h happens here too —
    keeps the table tiny.

    Safe to call concurrently with normal traffic (one-row-per-user
    updates only). Safe to call repeatedly — idempotent."""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        settings = get_settings(db)
        soft_days = int(settings.get("lifecycle.soft_delete_days") or 0)
        hard_days = int(settings.get("lifecycle.hard_delete_days") or 0)
        stats = {"soft_marked": 0, "hard_deleted": 0, "attempts_pruned": 0}

        now = datetime.utcnow()
        if soft_days > 0:
            soft_cutoff = now - timedelta(days=soft_days)
            soft_targets = (
                db.query(User)
                .filter(User.is_admin.is_(False))
                .filter(User.account_status == "active")
                .filter(User.last_active < soft_cutoff)
                .all()
            )
            for u in soft_targets:
                u.account_status = "dormant"
            stats["soft_marked"] = len(soft_targets)

        if hard_days > 0:
            hard_cutoff = now - timedelta(days=hard_days)
            hard_targets = (
                db.query(User)
                .filter(User.is_admin.is_(False))
                .filter(User.last_active < hard_cutoff)
                .all()
            )
            for u in hard_targets:
                db.delete(u)
            stats["hard_deleted"] = len(hard_targets)

        attempt_cutoff = now - timedelta(hours=24)
        pruned = (
            db.query(SignupAttempt)
            .filter(SignupAttempt.created_at < attempt_cutoff)
            .delete(synchronize_session=False)
        )
        stats["attempts_pruned"] = int(pruned or 0)

        db.commit()
        if stats["soft_marked"] or stats["hard_deleted"]:
            logger.info(
                "lifecycle pass: %d marked dormant, %d hard-deleted",
                stats["soft_marked"],
                stats["hard_deleted"],
            )
        return stats
    finally:
        if own_session:
            db.close()

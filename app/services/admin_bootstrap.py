"""Create the first admin account on an empty database."""

import logging
import secrets

from app.auth import get_password_hash
from app.core.paths import DATA_DIR
from app.database import SessionLocal, User

logger = logging.getLogger(__name__)


def ensure_admin() -> None:
    """Create user 'admin' with a random password when no users exist.

    The password is printed to the startup log and written to
    data/admin_bootstrap.txt (mode 0600), so a public deployment never ships
    a well-known default. The account must change it on first login."""
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        if user_count:
            logger.info(f"Found {user_count} existing user(s)")
            return
        password = secrets.token_urlsafe(16)
        db.add(
            User(
                username="admin",
                password_hash=get_password_hash(password),
                is_admin=True,
                must_change_password=True,
                invite_quota=-1,
            )
        )
        db.commit()

        try:
            bootstrap_file = DATA_DIR / "admin_bootstrap.txt"
            bootstrap_file.write_text(f"username: admin\npassword: {password}\n", encoding="utf-8")
            bootstrap_file.chmod(0o600)
        except Exception:
            # The file is a convenience; the log below always has the password.
            pass

        banner = "=" * 60
        logger.warning(banner)
        logger.warning("Initial admin user created — CHANGE PASSWORD ON FIRST LOGIN")
        logger.warning("  username: admin")
        logger.warning(f"  password: {password}")
        logger.warning("Also written to /app/data/admin_bootstrap.txt (mode 0600).")
        logger.warning(banner)
    except Exception as e:
        logger.error(f"Error setting up users: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

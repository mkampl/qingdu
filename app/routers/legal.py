"""
Public, unauthenticated endpoint exposing operator-supplied legal contact
details. Everything here comes from environment variables set by whoever
deploys this instance — nothing is hardcoded or committed to the repo, so
the maintainer's real name/address never lands in git history. See
.env.example for the variable names.

Both legal pages are opt-in and OFF by default:

- An Impressum is only considered "configured" once every field a §5 ECG /
  §5 TMG-style Anbieterkennzeichnung needs is present (name, full postal
  address, email). A self-hosted instance that leaves them unset simply
  has no Impressum page — the frontend hides the link and the route
  shows a neutral "not configured" state instead of fabricating one.
- The privacy page is OFF unless PRIVACY_PAGE_ENABLED is explicitly set
  to "true" — its content describes the maintainer's own demo server's
  specific data practices (which translation/TTS providers it calls,
  its retention windows) and would be misleading left on unedited for a
  different instance. Any other value, including unset, means off.
"""

import os

from fastapi import APIRouter

router = APIRouter(prefix="/api/legal", tags=["Legal"])


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _impressum() -> dict | None:
    name = _env("IMPRESSUM_NAME")
    street = _env("IMPRESSUM_STREET")
    zip_code = _env("IMPRESSUM_ZIP")
    city = _env("IMPRESSUM_CITY")
    email = _env("IMPRESSUM_EMAIL")
    if not (name and street and zip_code and city and email):
        return None
    return {
        "name": name,
        "street": street,
        "zip": zip_code,
        "city": city,
        "country": _env("IMPRESSUM_COUNTRY") or None,
        "email": email,
        "phone": _env("IMPRESSUM_PHONE") or None,
        # Freeform line for whatever else the operator's local law
        # requires (VAT ID, Medieninhaber/editorial-responsibility line,
        # professional register, supervisory authority, ...). Supports
        # literal "\n" for multiple lines since .env files can't hold
        # real newlines.
        "extra": _env("IMPRESSUM_EXTRA").replace("\\n", "\n") or None,
    }


@router.get("", summary="Operator-configured legal page availability")
async def legal_config():
    return {
        "impressum": _impressum(),
        "privacy_enabled": _env("PRIVACY_PAGE_ENABLED").lower() == "true",
    }

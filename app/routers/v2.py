"""
Mounts the Vue 3 SPA built by `frontend/` under `/v2`.

The Vite build emits to `frontend/dist`. The Dockerfile copies that dir to
`/app/frontend/dist` so we can serve it as static assets here. Any URL under
`/v2/...` that doesn't match an asset falls back to `index.html` for client-side
routing (history-mode router).
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.paths import BASE_DIR

router = APIRouter()

V2_DIST = BASE_DIR / "frontend" / "dist"
V2_ASSETS = V2_DIST / "assets"


def mount(app):
    """Attach the SPA to `app`. Call from main.py."""
    if not V2_DIST.exists():
        # No build artefact — skip the mount so the rest of the app still boots.
        return

    # /v2/assets/<file> — Vite-emitted hashed assets.
    app.mount(
        "/v2/assets",
        StaticFiles(directory=str(V2_ASSETS)),
        name="v2-assets",
    )
    # /v2 and any deeper path — serve index.html so Vue Router handles routing.
    app.include_router(router)


@router.get("/v2", include_in_schema=False)
@router.get("/v2/{rest:path}", include_in_schema=False)
async def v2_spa(request: Request, rest: str | None = None):
    """SPA fallback — return index.html for any unknown sub-path."""
    index = V2_DIST / "index.html"
    if not index.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend not built. Run `npm --prefix frontend run build`.",
        )
    # If the request is for a specific file at the root of dist/, serve it
    # (favicons, manifest, etc. would normally come from /static, but allow it).
    if rest:
        candidate: Path = V2_DIST / rest
        if candidate.is_file() and candidate.resolve().is_relative_to(V2_DIST.resolve()):
            return FileResponse(candidate)
    return FileResponse(index)

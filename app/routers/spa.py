"""
Mounts the Vue 3 SPA built by `frontend/` at the site root `/`.

The Vite build emits to `frontend/dist`. The Dockerfile copies that dir to
`/app/frontend/dist` so we can serve it as static assets here. Any URL that
isn't matched by a more-specific API/static route falls back to `index.html`
for client-side routing (history-mode router).

`/v2/*` paths are kept around as permanent redirects to `/*` so the bookmarks
and invite links generated during the `/v2`-staging period keep working.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.paths import BASE_DIR

router = APIRouter()

SPA_DIST = BASE_DIR / "frontend" / "dist"
SPA_ASSETS = SPA_DIST / "assets"


def mount(app):
    """Attach the SPA to `app`. Call from main.py *after* all API routers."""
    if not SPA_DIST.exists():
        # No build artefact — skip the mount so the rest of the app still boots
        # (e.g. CI / pytest without the frontend build step).
        return

    # /assets/<file> — Vite-emitted hashed assets.
    app.mount(
        "/assets",
        StaticFiles(directory=str(SPA_ASSETS)),
        name="spa-assets",
    )
    app.include_router(router)


# Legacy /v2/* paths from the staging period — keep them working forever by
# redirecting to the same path under /. FastAPI's RedirectResponse preserves
# the query string when present (no extra work needed for `?invite=…`).
@router.get("/v2", include_in_schema=False)
async def v2_root_redirect(request: Request):
    qs = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"/{qs}", status_code=301)


@router.get("/v2/{rest:path}", include_in_schema=False)
async def v2_subpath_redirect(rest: str, request: Request):
    qs = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"/{rest}{qs}", status_code=301)


# Root and SPA fallback. Registered LAST in main.py via mount() so it doesn't
# swallow /api/*, /static/*, /health, etc.
@router.get("/", include_in_schema=False)
@router.get("/{rest:path}", include_in_schema=False)
async def spa_fallback(request: Request, rest: str | None = None):
    """Serve index.html so Vue Router can take it from there."""
    index = SPA_DIST / "index.html"
    if not index.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend not built. Run `npm --prefix frontend run build`.",
        )
    # If the request is for a file at the root of dist/ (favicons, manifest,
    # robots.txt, etc.), serve it directly. Otherwise fall through to the
    # SPA shell.
    if rest:
        candidate: Path = SPA_DIST / rest
        if candidate.is_file() and candidate.resolve().is_relative_to(SPA_DIST.resolve()):
            return FileResponse(candidate)
    return FileResponse(index)

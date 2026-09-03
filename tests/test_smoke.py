"""Smoke tests — assert the app boots and the route table looks right."""


def test_app_imports(app_module):
    """The app should import without exceptions."""
    assert app_module is not None


def test_route_count(app_module):
    """The route count is a coarse regression detector — bump intentionally.

    96 = API routes alone (Phase 2.7 added 6, practice-mode 1, the
    2026-07 audit's trust pair 2: GET /api/auth/export, DELETE /api/auth/me,
    library reading-progress added 5: GET /api/library/progress,
    POST + DELETE /api/library/{slug}/read, GET + POST /api/library/{slug}/quiz,
    and GET /api/legal for the configurable Impressum/privacy pages).
    +5 = 101 when the Vite frontend is built into `frontend/dist/`:
    /v2 redirect, /v2/{rest} redirect, / SPA shell, /{rest:path} SPA shell,
    /assets mount.
    +5 = 101/106 for Phase #121's external-integration API: GET + POST +
    DELETE /api/tokens[/{id}] and GET /api/external/words, POST
    /api/external/words/encountered.
    -1 = 100/105 for the 2026-08-06 removal of POST /api/pronounce (the
    Whisper + librosa pronunciation-check feature — retired for its
    dependency weight; see the qingdu-pronunciation-check.md writeup in
    the companion project for the retrospective).
    +1 = 101/106 for the 2026-09-03 watch-and-read prototype's
    POST /api/media/youtube (spike, not a shipped feature yet).
    """
    assert len(app_module.routes) in (101, 106)


def test_router_tags_present(app_module):
    """The 13 API routers should be wired (Pages was retired at cutover)."""
    tags = set()
    for r in app_module.routes:
        if hasattr(r, "tags") and r.tags:
            tags.update(r.tags)
    expected = {
        "Admin",
        "Analysis",
        "Anki Export",
        "Authentication",
        "Invitations",
        "Saved Texts",
        "System",
        "TTS",
        "Translation",
        "Vocabulary",
        "Vocabulary Lists",
        "Words",
        "Review",
        "Convert",
        "Stats",
        "Export",
        "Package Import",
        "Library",
        "API Tokens",
        "External API",
    }
    assert expected.issubset(tags), f"Missing tags: {expected - tags}"


def test_health_endpoint_present(app_module):
    """The /health route should exist (used by Docker healthcheck)."""
    paths = {getattr(r, "path", None) for r in app_module.routes}
    assert "/health" in paths


def test_translate_route_present(app_module):
    paths = {getattr(r, "path", None) for r in app_module.routes}
    assert "/api/translate" in paths

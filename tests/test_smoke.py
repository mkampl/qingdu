"""Smoke tests — assert the app boots and the route table looks right."""


def test_app_imports(app_module):
    """The app should import without exceptions."""
    assert app_module is not None


def test_route_count(app_module):
    """The route count is a coarse regression detector — bump intentionally.

    92 = API routes alone (Phase 2.7 adds 6: GET /api/auth/captcha,
    GET /api/auth/registration-status, POST /api/auth/register,
    GET /api/admin/registration-settings,
    PATCH /api/admin/registration-settings,
    POST /api/admin/lifecycle/run-now).
    +5 when the Vite frontend is built into `frontend/dist/`: /v2 redirect,
    /v2/{rest} redirect, / SPA shell, /{rest:path} SPA shell, /assets mount.
    """
    assert len(app_module.routes) in (92, 97)


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
        "Pronounce",
        "Library",
    }
    assert expected.issubset(tags), f"Missing tags: {expected - tags}"


def test_health_endpoint_present(app_module):
    """The /health route should exist (used by Docker healthcheck)."""
    paths = {getattr(r, "path", None) for r in app_module.routes}
    assert "/health" in paths


def test_translate_route_present(app_module):
    paths = {getattr(r, "path", None) for r in app_module.routes}
    assert "/api/translate" in paths

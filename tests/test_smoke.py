"""Smoke tests — assert the app boots and the route table looks right."""


def test_app_imports(app_module):
    """The app should import without exceptions."""
    assert app_module is not None


def test_route_count(app_module):
    """The route count is a coarse regression detector — bump intentionally.

    47 = API routes alone (no Pages router; legacy templates retired;
    includes /api/admin/translate-providers healthcheck).
    +5 when the Vite frontend is built into `frontend/dist/`: /v2 redirect,
    /v2/{rest} redirect, / SPA shell, /{rest:path} SPA shell, /assets mount.
    """
    assert len(app_module.routes) in (47, 52)


def test_router_tags_present(app_module):
    """The 11 API routers should be wired (Pages was retired at cutover)."""
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
    }
    assert expected.issubset(tags), f"Missing tags: {expected - tags}"


def test_health_endpoint_present(app_module):
    """The /health route should exist (used by Docker healthcheck)."""
    paths = {getattr(r, "path", None) for r in app_module.routes}
    assert "/health" in paths


def test_translate_route_present(app_module):
    paths = {getattr(r, "path", None) for r in app_module.routes}
    assert "/api/translate" in paths

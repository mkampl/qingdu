"""Smoke tests — assert the app boots and the route table looks right."""


def test_app_imports(app_module):
    """The app should import without exceptions."""
    assert app_module is not None


def test_route_count(app_module):
    """The route count is a coarse regression detector — bump intentionally.

    48 = API/page routes alone. +3 when the Vite frontend is built into
    `frontend/dist/` (two SPA fallbacks + a /v2/assets static mount).
    """
    assert len(app_module.routes) in (48, 51)


def test_router_tags_present(app_module):
    """All 12 routers should be wired."""
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
        "Pages",
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

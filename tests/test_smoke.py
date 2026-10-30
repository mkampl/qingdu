"""Smoke tests — assert the app boots and the route table looks right."""


def test_app_imports(app_module):
    """The app should import without exceptions."""
    assert app_module is not None


def test_route_count(app_module):
    """A coarse check on the route table; change it on purpose, in the same
    commit that adds or removes an endpoint.

    133 = API routes alone. +5 = 138 when the Vite frontend is built into
    `frontend/dist/`: /v2 redirect, /v2/{rest} redirect, / SPA shell,
    /{rest:path} SPA shell, /assets mount.
    """
    assert len(app_module.routes) in (133, 138)


def test_router_tags_present(app_module):
    """Every API router is wired, by tag."""
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

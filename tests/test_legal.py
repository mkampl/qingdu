"""GET /api/legal — operator-configured Impressum/privacy availability."""

# The required trio — street/zip/country/phone/extra are all optional,
# see test_street_and_zip_are_optional.
IMPRESSUM_VARS = {
    "IMPRESSUM_NAME": "Jane Doe",
    "IMPRESSUM_CITY": "Vienna",
    "IMPRESSUM_EMAIL": "jane@example.com",
}


def test_unconfigured_by_default(client, monkeypatch):
    """Both legal pages are opt-in: no env vars set means both are off."""
    for var in (*IMPRESSUM_VARS, "IMPRESSUM_COUNTRY", "IMPRESSUM_PHONE", "IMPRESSUM_EXTRA"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("PRIVACY_PAGE_ENABLED", raising=False)

    r = client.get("/api/legal")
    assert r.status_code == 200
    body = r.json()
    assert body["impressum"] is None
    assert body["privacy_enabled"] is False


def test_privacy_requires_exact_opt_in(client, monkeypatch):
    """Only the literal string "true" turns the privacy page on — a typo
    or a loosely-truthy value ("1", "yes") must not silently publish it."""
    for value in ("1", "yes", "enabled", ""):
        monkeypatch.setenv("PRIVACY_PAGE_ENABLED", value)
        assert client.get("/api/legal").json()["privacy_enabled"] is False

    # Case and surrounding whitespace are tolerated for the one string
    # that does enable it — deployers shouldn't get bitten by a stray
    # newline or capitalisation in their .env file.
    for value in ("true", "TRUE", " true "):
        monkeypatch.setenv("PRIVACY_PAGE_ENABLED", value)
        assert client.get("/api/legal").json()["privacy_enabled"] is True


def test_partial_config_stays_unconfigured(client, monkeypatch):
    # Missing IMPRESSUM_EMAIL — a half-filled Impressum is not a valid one.
    for key, value in IMPRESSUM_VARS.items():
        if key != "IMPRESSUM_EMAIL":
            monkeypatch.setenv(key, value)
    monkeypatch.delenv("IMPRESSUM_EMAIL", raising=False)
    monkeypatch.delenv("IMPRESSUM_STREET", raising=False)
    monkeypatch.delenv("IMPRESSUM_ZIP", raising=False)

    assert client.get("/api/legal").json()["impressum"] is None


def test_street_and_zip_are_optional(client, monkeypatch):
    """An operator can publish just name + city + email (place of
    residence) without a full street address — only the trio is required."""
    for key, value in IMPRESSUM_VARS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("IMPRESSUM_STREET", raising=False)
    monkeypatch.delenv("IMPRESSUM_ZIP", raising=False)

    body = client.get("/api/legal").json()["impressum"]
    assert body is not None
    assert body["street"] is None
    assert body["zip"] is None
    assert body["city"] == "Vienna"


def test_full_config_returns_impressum(client, monkeypatch):
    """The two flags are independent — Impressum can be configured while
    privacy stays off (its default), or vice versa."""
    for key, value in IMPRESSUM_VARS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("IMPRESSUM_EXTRA", "VAT: ATU12345678\\nLine two")
    monkeypatch.delenv("PRIVACY_PAGE_ENABLED", raising=False)

    body = client.get("/api/legal").json()
    assert body["impressum"]["name"] == "Jane Doe"
    assert body["impressum"]["email"] == "jane@example.com"
    assert body["impressum"]["extra"] == "VAT: ATU12345678\nLine two"
    assert body["impressum"]["country"] is None
    assert body["privacy_enabled"] is False

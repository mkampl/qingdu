"""
Script conversion + heuristic detection. The actual OpenCC mapping is the
upstream library's responsibility; here we verify our HTTP shape and
sanity-check the detect heuristic.
"""

from fastapi.testclient import TestClient


def test_t2s_converts_traditional_to_simplified(app_module):
    with TestClient(app_module) as client:
        r = client.post(
            "/api/convert",
            json={"text": "我是昨天來的。", "direction": "t2s"},
        )
        assert r.status_code == 200
        assert r.json() == {"converted": "我是昨天来的。", "direction": "t2s"}


def test_s2t_converts_simplified_to_traditional(app_module):
    with TestClient(app_module) as client:
        r = client.post(
            "/api/convert",
            json={"text": "我是昨天来的。", "direction": "s2t"},
        )
        assert r.status_code == 200
        assert r.json()["converted"] == "我是昨天來的。"


def test_empty_text_returns_empty(app_module):
    with TestClient(app_module) as client:
        r = client.post("/api/convert", json={"text": "", "direction": "t2s"})
        assert r.status_code == 200
        assert r.json()["converted"] == ""


def test_detect_traditional(app_module):
    with TestClient(app_module) as client:
        r = client.post(
            "/api/convert/detect",
            json={"text": "我是昨天來的。天氣越來越冷。"},
        )
        assert r.status_code == 200
        assert r.json()["script"] == "traditional"


def test_detect_simplified(app_module):
    with TestClient(app_module) as client:
        r = client.post(
            "/api/convert/detect",
            json={"text": "我是昨天来的。天气越来越冷。"},
        )
        assert r.status_code == 200
        # Simplified text shouldn't round-trip-change under t2s.
        assert r.json()["script"] == "simplified"


def test_detect_empty_is_unknown(app_module):
    with TestClient(app_module) as client:
        r = client.post("/api/convert/detect", json={"text": ""})
        assert r.json()["script"] == "unknown"

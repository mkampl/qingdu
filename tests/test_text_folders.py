"""Folders of saved texts: nesting, moving, order, and a text's place in
its folder (number + previous / next)."""

import pytest

from app.database import SavedText, TextFolder, User

ANALYSIS = {"words": [{"text": "你好", "translation_source": "hsk"}], "statistics": {}}


@pytest.fixture
def client(memory_db, open_client):
    Session = memory_db
    s = Session()
    s.add(User(id=1, username="alice", password_hash="x", must_change_password=False))
    s.add(User(id=2, username="bob", password_hash="x", must_change_password=False))
    s.commit()
    s.close()

    return open_client(Session)


def _folder(c, name, parent_id=None):
    r = c.post("/api/folders", json={"name": name, "parent_id": parent_id})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _save(c, title, folder_id=None):
    r = c.post(
        "/api/texts/save",
        json={"title": title, "content": "你好", "analysis_data": ANALYSIS, "folder_id": folder_id},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_texts_saved_into_a_folder_are_numbered_in_order(client):
    top = _folder(client, "TaiJiMen")
    ddj = _folder(client, "道德经", top)
    ids = [_save(client, f"part {i}", ddj) for i in range(1, 4)]
    loose = _save(client, "loose")

    series = client.get(f"/api/texts/{ids[1]}").json()["series"]
    assert series["index"] == 2 and series["count"] == 3
    assert series["prev_id"] == ids[0] and series["next_id"] == ids[2]
    assert [p["name"] for p in series["path"]] == ["TaiJiMen", "道德经"]
    assert client.get(f"/api/texts/{loose}").json()["series"] is None

    summaries = {t["id"]: t for t in client.get("/api/texts").json()}
    assert summaries[ids[0]]["folder_id"] == ddj
    assert summaries[loose]["folder_id"] is None


def test_reordering_a_folder(client):
    f = _folder(client, "Book")
    a, b, c = (_save(client, t, f) for t in "abc")
    r = client.post("/api/texts/order", json={"folder_id": f, "text_ids": [c, a, b]})
    assert r.status_code == 200
    assert client.get(f"/api/texts/{c}").json()["series"]["index"] == 1
    assert client.get(f"/api/texts/{b}").json()["series"]["next_id"] is None
    # Every text of the folder, once.
    r = client.post("/api/texts/order", json={"folder_id": f, "text_ids": [a, b]})
    assert r.status_code == 400


def test_moving_a_text_appends_it_to_the_new_folder(client):
    f = _folder(client, "Book")
    a = _save(client, "a", f)
    loose = _save(client, "loose")
    assert client.patch(f"/api/texts/{loose}", json={"folder_id": f}).status_code == 200
    series = client.get(f"/api/texts/{loose}").json()["series"]
    assert (series["index"], series["prev_id"]) == (2, a)
    client.patch(f"/api/texts/{loose}", json={"folder_id": None})
    assert client.get(f"/api/texts/{loose}").json()["series"] is None


def test_a_folder_cannot_move_into_itself(client):
    top = _folder(client, "top")
    sub = _folder(client, "sub", top)
    r = client.patch(f"/api/folders/{top}", json={"move": True, "parent_id": sub})
    assert r.status_code == 400
    r = client.patch(f"/api/folders/{sub}", json={"move": True, "parent_id": None})
    assert r.status_code == 200 and r.json()["parent_id"] is None
    r = client.patch(f"/api/folders/{sub}", json={"name": "renamed"})
    assert r.json()["name"] == "renamed" and r.json()["parent_id"] is None


def test_deleting_a_folder_keeps_its_texts(client):
    top = _folder(client, "top")
    mid = _folder(client, "mid", top)
    sub = _folder(client, "sub", mid)
    t = _save(client, "t", mid)
    assert client.delete(f"/api/folders/{mid}").status_code == 200
    s = client.session_factory()
    assert s.get(SavedText, t).folder_id == top
    assert s.get(TextFolder, sub).parent_id == top
    s.close()


def test_folders_of_other_users_are_off_limits(client):
    s = client.session_factory()
    s.add(TextFolder(id=99, user_id=2, name="bob's"))
    s.commit()
    s.close()
    assert client.post("/api/folders", json={"name": "x", "parent_id": 99}).status_code == 404
    t = _save(client, "t")
    assert client.patch(f"/api/texts/{t}", json={"folder_id": 99}).status_code == 404
    r = client.post(
        "/api/texts/save",
        json={"title": "x", "content": "你好", "analysis_data": ANALYSIS, "folder_id": 99},
    )
    assert r.status_code == 404
    assert [f["id"] for f in client.get("/api/folders").json()] == []

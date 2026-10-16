"""Pinned dictionary data: vendored files, checksum checks, the dictionary
version and the version-gated user-word snapshot refresh."""

import gzip
import hashlib
import json

import pytest

from app import state
from app.services import dict_data, snapshot_backfill

TINY_HSK = [
    {
        "simplified": "地",
        "radical": "土",
        "level": ["new-1", "old-1"],
        "frequency": 10,
        "forms": [
            {
                "traditional": "地",
                "transcriptions": {"pinyin": "dì"},
                "meanings": ["earth; ground"],
            }
        ],
    },
    {
        "simplified": "学生",
        "radical": "子",
        "level": ["new-1", "old-1"],
        "frequency": 50,
        "forms": [
            {
                "traditional": "學生",
                "transcriptions": {"pinyin": "xuésheng"},
                "meanings": ["student"],
            }
        ],
    },
]

TINY_CEDICT = (
    "# CC-CEDICT test snippet\n"
    "#! date=2026-01-01T00:00:00Z\n"
    "地 地 [di4] /earth/ground/\n"
    "學生 学生 [xue2 sheng5] /student/schoolchild/\n"
)


def _write_dict_dir(path, hsk=TINY_HSK, cedict=TINY_CEDICT):
    path.mkdir(parents=True, exist_ok=True)
    hsk_bytes = json.dumps(hsk, ensure_ascii=False).encode("utf-8")
    cedict_bytes = cedict.encode("utf-8")
    (path / "hsk.json.gz").write_bytes(gzip.compress(hsk_bytes))
    (path / "cedict.u8.gz").write_bytes(gzip.compress(cedict_bytes))
    version = {
        "hsk": {"file": "hsk.json.gz", "sha256": hashlib.sha256(hsk_bytes).hexdigest()},
        "cedict": {"file": "cedict.u8.gz", "sha256": hashlib.sha256(cedict_bytes).hexdigest()},
    }
    (path / "VERSION.json").write_text(json.dumps(version), encoding="utf-8")
    return path


@pytest.fixture
def saved_state():
    """Restore the shared dictionaries after a test swaps them out."""
    saved = (
        dict(state.hsk_vocab),
        dict(state.hsk_lists_original),
        dict(state.cedict_vocab),
        dict(dict_data.loaded_sources),
    )
    yield
    for target, copy in zip(
        (state.hsk_vocab, state.hsk_lists_original, state.cedict_vocab, dict_data.loaded_sources),
        saved,
        strict=True,
    ):
        target.clear()
        target.update(copy)


# ---- the vendored files in the repo ------------------------------------


def test_vendored_files_match_version_json():
    info = dict_data.read_version_info()
    assert info["hsk"]["commit"], "HSK source must be pinned to a commit"
    for source in ("hsk", "cedict", "makemeahanzi"):
        found = dict_data.read_vendored(source)
        assert found is not None, f"{source} file missing from app/data/dict"
        _data, digest = found
        assert digest == info[source]["sha256"]


def test_vendored_cedict_header_matches_version_date():
    data, _ = dict_data.read_vendored("cedict")
    header = data[:2000].decode("utf-8")
    assert f"#! date={dict_data.read_version_info()['cedict']['date']}" in header


def test_checksum_mismatch_is_rejected(tmp_path):
    d = _write_dict_dir(tmp_path / "dict")
    info = json.loads((d / "VERSION.json").read_text())
    info["cedict"]["sha256"] = "0" * 64
    (d / "VERSION.json").write_text(json.dumps(info))
    with pytest.raises(dict_data.ChecksumError):
        dict_data.read_vendored("cedict", d)


def test_missing_file_reads_as_none(tmp_path):
    d = _write_dict_dir(tmp_path / "dict")
    (d / "hsk.json.gz").unlink()
    assert dict_data.read_vendored("hsk", d) is None
    assert dict_data.read_vendored("hsk", tmp_path / "nowhere") is None


# ---- dictionary version -------------------------------------------------


def test_dict_version_needs_both_sources(monkeypatch):
    monkeypatch.setitem(dict_data.loaded_sources, "hsk", "a" * 64)
    monkeypatch.setitem(dict_data.loaded_sources, "cedict", None)
    assert dict_data.dict_version() is None
    monkeypatch.setitem(dict_data.loaded_sources, "cedict", "b" * 64)
    assert dict_data.dict_version() is not None


def test_dict_version_changes_with_data_and_rules(monkeypatch):
    monkeypatch.setitem(dict_data.loaded_sources, "hsk", "a" * 64)
    monkeypatch.setitem(dict_data.loaded_sources, "cedict", "b" * 64)
    v1 = dict_data.dict_version()
    assert dict_data.dict_version() == v1
    monkeypatch.setitem(dict_data.loaded_sources, "cedict", "c" * 64)
    v2 = dict_data.dict_version()
    assert v2 != v1
    monkeypatch.setattr(dict_data, "GLOSS_RULES_VERSION", 999)
    assert dict_data.dict_version() != v2


# ---- version-gated backfill ---------------------------------------------


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Persistent throwaway SQLite file wired into app.database."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import database

    engine = create_engine(
        f"sqlite:///{tmp_path / 'qingdu.db'}", connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(database, "engine", engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(database, "SessionLocal", Session)
    database.Base.metadata.create_all(bind=engine)
    return Session


def _add_word(Session, word, meaning, pinyin="x"):
    from app.database import User, UserWord

    s = Session()
    if not s.query(User).filter(User.id == 1).first():
        s.add(User(id=1, username="alice", password_hash="x", invite_quota=0))
    s.add(UserWord(user_id=1, word=word, state="learning", pinyin=pinyin, meaning=meaning))
    s.commit()
    s.close()


def _meaning(Session, word):
    from app.database import UserWord

    s = Session()
    try:
        return s.query(UserWord).filter(UserWord.word == word).one().meaning
    finally:
        s.close()


def test_backfill_runs_when_no_version_stored_then_skips(temp_db, saved_state, monkeypatch):
    state.hsk_vocab.clear()
    state.cedict_vocab.clear()
    state.hsk_vocab["地"] = {"pinyin": "dì", "meaning": "earth", "meanings": ["earth"]}
    monkeypatch.setitem(dict_data.loaded_sources, "hsk", "a" * 64)
    monkeypatch.setitem(dict_data.loaded_sources, "cedict", "b" * 64)
    _add_word(temp_db, "地", "-ly")

    # First boot after the upgrade: nothing stored yet, so it must run.
    s = temp_db()
    assert dict_data.get_stored_version(s) is None
    s.close()
    assert snapshot_backfill.run_at_startup() == 1
    assert _meaning(temp_db, "地") == "earth"
    s = temp_db()
    assert dict_data.get_stored_version(s) == dict_data.dict_version()
    s.close()

    # Same version: the row is left alone even if it no longer matches.
    from app.database import UserWord

    s = temp_db()
    s.query(UserWord).filter(UserWord.word == "地").one().meaning = "stale"
    s.commit()
    s.close()
    assert snapshot_backfill.run_at_startup() is None
    assert _meaning(temp_db, "地") == "stale"

    # New version: runs again.
    monkeypatch.setitem(dict_data.loaded_sources, "cedict", "c" * 64)
    assert snapshot_backfill.run_at_startup() == 1
    assert _meaning(temp_db, "地") == "earth"


def test_backfill_skipped_when_dictionary_incomplete(temp_db, saved_state, monkeypatch):
    monkeypatch.setitem(dict_data.loaded_sources, "cedict", None)
    _add_word(temp_db, "地", "-ly")
    assert snapshot_backfill.run_at_startup() is None
    assert _meaning(temp_db, "地") == "-ly"
    s = temp_db()
    assert dict_data.get_stored_version(s) is None
    s.close()


# ---- smoke: full app startup twice ---------------------------------------


def test_restart_does_not_rewrite_user_words(
    app_module, tmp_path, temp_db, saved_state, monkeypatch
):
    from fastapi.testclient import TestClient

    from app.services import cedict_loader, hsk_loader

    monkeypatch.delenv("QINGDU_SKIP_CEDICT_LOAD", raising=False)
    monkeypatch.setattr(dict_data, "DICT_DIR", _write_dict_dir(tmp_path / "dict"))
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(hsk_loader, "DATA_DIR", runtime)
    monkeypatch.setattr(cedict_loader, "CEDICT_CACHE_FILE", runtime / "cedict_ts.u8")

    _add_word(temp_db, "学生", "old gloss")

    with TestClient(app_module):
        pass
    # First boot: no stored version yet, so the snapshot was refreshed.
    assert _meaning(temp_db, "学生") == "student"
    s = temp_db()
    first_version = dict_data.get_stored_version(s)
    s.close()
    assert first_version is not None

    # Simulate a user-visible value the backfill would otherwise rewrite.
    from app.database import UserWord

    s = temp_db()
    s.query(UserWord).filter(UserWord.word == "学生").one().meaning = "kept"
    s.commit()
    s.close()

    with TestClient(app_module):
        pass
    assert _meaning(temp_db, "学生") == "kept"
    s = temp_db()
    assert dict_data.get_stored_version(s) == first_version
    s.close()


# ---- loader fallbacks ------------------------------------------------------


async def test_vendored_hsk_loads_and_records_hash(tmp_path, monkeypatch, saved_state):
    from app.services import hsk_loader

    d = _write_dict_dir(tmp_path / "dict")
    monkeypatch.setattr(dict_data, "DICT_DIR", d)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(hsk_loader, "DATA_DIR", runtime)

    await hsk_loader.load_hsk_vocabulary()
    assert state.hsk_vocab["学生"]["level_new"] == "new-1"
    expected = json.loads((d / "VERSION.json").read_text())["hsk"]["sha256"]
    assert dict_data.loaded_sources["hsk"] == expected
    assert (runtime / "hsk_vocabulary.json").exists()


async def test_corrupt_vendored_hsk_falls_back_to_cache(tmp_path, monkeypatch, saved_state):
    from app.services import hsk_loader

    d = _write_dict_dir(tmp_path / "dict")
    info = json.loads((d / "VERSION.json").read_text())
    info["hsk"]["sha256"] = "0" * 64  # no commit recorded either, so no download
    (d / "VERSION.json").write_text(json.dumps(info))
    monkeypatch.setattr(dict_data, "DICT_DIR", d)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cached = {"猫": {"pinyin": "māo", "meaning": "cat"}}
    (runtime / "hsk_vocabulary.json").write_text(json.dumps(cached), encoding="utf-8")
    monkeypatch.setattr(hsk_loader, "DATA_DIR", runtime)

    await hsk_loader.load_hsk_vocabulary()
    assert state.hsk_vocab == cached
    # Unpinned data: no dictionary version, so user rows are not rewritten.
    assert dict_data.loaded_sources["hsk"] is None
    assert dict_data.dict_version() is None


# ---- tools/refresh_dictionaries.py ---------------------------------------


@pytest.fixture
def refresh_tool():
    import importlib
    import sys
    from pathlib import Path

    tools_dir = str(Path(__file__).resolve().parent.parent / "tools")
    sys.path.insert(0, tools_dir)
    try:
        yield importlib.import_module("refresh_dictionaries")
    finally:
        sys.path.remove(tools_dir)


def test_refresh_tool_dry_run_and_write(
    tmp_path, monkeypatch, saved_state, refresh_tool, capsys, no_learner_glosses
):
    # Without the learner layer: 学生 has a learner gloss, which would hide
    # the CC-CEDICT headline change this test feeds the tool.
    d = _write_dict_dir(tmp_path / "dict")
    info = json.loads((d / "VERSION.json").read_text())
    info["hsk"]["commit"] = "abc"
    (d / "VERSION.json").write_text(json.dumps(info))
    monkeypatch.setattr(refresh_tool, "DICT_DIR", d)
    monkeypatch.setattr(refresh_tool, "VERSION_FILE", d / "VERSION.json")

    new_cedict = TINY_CEDICT.replace("/student/schoolchild/", "/pupil/student/")
    src = tmp_path / "new_cedict.u8"
    src.write_text(new_cedict, encoding="utf-8")
    args = ["--skip-hsk", "--cedict-file", str(src)]

    before = (d / "VERSION.json").read_text()
    assert refresh_tool.main([*args, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "学生" in out and "'student'  ->  'pupil'" in out
    assert (d / "VERSION.json").read_text() == before

    assert refresh_tool.main(args) == 0
    data, digest = dict_data.read_vendored("cedict", d)
    assert data.decode("utf-8") == new_cedict
    written = json.loads((d / "VERSION.json").read_text())
    assert written["cedict"]["sha256"] == digest
    assert written["cedict"]["date"] == "2026-01-01T00:00:00Z"
    assert written["hsk"]["commit"] == "abc"

    # A second run with the same input finds nothing to do.
    assert refresh_tool.main(args) == 0
    assert "Nothing changed" in capsys.readouterr().out

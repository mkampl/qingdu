#!/usr/bin/env python3
"""Replace the pinned dictionary files with newer upstream versions.

Downloads the HSK list (drkameleon/complete-hsk-vocabulary, at the current
``main`` commit or ``--hsk-ref``) and mdbg's current CC-CEDICT export,
writes them into ``app/data/dict/`` together with an updated
``VERSION.json``, and prints the gloss diff (``tools/gloss_audit.py``)
between the old and the new files.

Never runs automatically. Typical use::

    python tools/refresh_dictionaries.py --dry-run     # look at the diff only
    python tools/refresh_dictionaries.py               # write the new files
    pytest -q tests/test_golden_glosses.py             # golden set must stay green
    git diff --stat app/data/dict && git commit ...

``--hsk-file`` / ``--cedict-file`` take local copies instead of
downloading (plain or gzipped). After a refresh the dictionary version
changes, so the next app start rewrites the pinyin/meaning snapshots on
users' words once.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import gloss_audit  # noqa: E402

DICT_DIR = REPO_ROOT / "app" / "data" / "dict"
VERSION_FILE = DICT_DIR / "VERSION.json"
HSK_REPO = "drkameleon/complete-hsk-vocabulary"
HSK_FILE = "complete-hsk-vocabulary.json.gz"
CEDICT_FILE = "cedict_ts.u8.gz"


def _get(url: str) -> bytes:
    import httpx

    r = httpx.get(url, timeout=60.0, follow_redirects=True)
    r.raise_for_status()
    return r.content


def _plain(data: bytes) -> bytes:
    return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data


def _resolve_hsk_commit(ref: str) -> tuple[str, str]:
    info = json.loads(_get(f"https://api.github.com/repos/{HSK_REPO}/commits/{ref}"))
    return info["sha"], info["commit"]["committer"]["date"]


def _cedict_header(text: str) -> dict[str, str]:
    header = {}
    for line in text.splitlines()[:60]:
        m = re.match(r"#! (\w+)=(.*)", line)
        if m:
            header[m.group(1)] = m.group(2).strip()
    return header


def _write_gz(path: Path, data: bytes) -> None:
    # mtime=0 keeps the archive byte-identical for identical content.
    path.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))


def main(argv: list[str] | None = None) -> int:
    from app.core.constants import CEDICT_URL, HSK_VOCAB_URL_TEMPLATE

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hsk-ref", default="main", help="branch, tag or commit (default: main)")
    ap.add_argument("--hsk-file", help="use this complete.json[.gz] instead of downloading")
    ap.add_argument("--cedict-file", help="use this cedict_ts.u8[.gz] instead of downloading")
    ap.add_argument("--skip-hsk", action="store_true", help="keep the current HSK file")
    ap.add_argument("--skip-cedict", action="store_true", help="keep the current CC-CEDICT")
    ap.add_argument("--dry-run", action="store_true", help="show the diff, write nothing")
    ap.add_argument("--level", type=int, action="append", help="diff only this HSK level")
    ap.add_argument("--limit", type=int, default=40, help="rows per diff group (0 = all)")
    args = ap.parse_args(argv)

    version = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    new_version = json.loads(json.dumps(version))
    staged: dict[str, bytes] = {}

    if not args.skip_hsk:
        if args.hsk_file:
            data = _plain(Path(args.hsk_file).read_bytes())
            commit, commit_date = None, None
            print(f"HSK: local file {args.hsk_file}")
        else:
            commit, commit_date = _resolve_hsk_commit(args.hsk_ref)
            url = HSK_VOCAB_URL_TEMPLATE.format(ref=commit)
            print(f"HSK: downloading {url}")
            data = _get(url)
        json.loads(data)  # must parse
        digest = hashlib.sha256(data).hexdigest()
        entry = new_version["hsk"]
        entry.update(file=HSK_FILE, sha256=digest)
        if commit:
            entry.update(commit=commit, commit_date=commit_date)
        else:
            entry.update(commit=None, commit_date=None, note=f"from local file {args.hsk_file}")
        if digest == version["hsk"].get("sha256"):
            print("HSK: unchanged")
        else:
            staged[HSK_FILE] = data

    if not args.skip_cedict:
        if args.cedict_file:
            data = _plain(Path(args.cedict_file).read_bytes())
            print(f"CC-CEDICT: local file {args.cedict_file}")
        else:
            print(f"CC-CEDICT: downloading {CEDICT_URL}")
            data = _plain(_get(CEDICT_URL))
        header = _cedict_header(data.decode("utf-8"))
        digest = hashlib.sha256(data).hexdigest()
        entry = new_version["cedict"]
        entry.update(file=CEDICT_FILE, sha256=digest, date=header.get("date"))
        if header.get("entries", "").isdigit():
            entry["entries"] = int(header["entries"])
        if digest == version["cedict"].get("sha256"):
            print("CC-CEDICT: unchanged")
        else:
            staged[CEDICT_FILE] = data

    if not staged:
        print("Nothing changed.")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        new_paths = {
            HSK_FILE: DICT_DIR / version["hsk"]["file"],
            CEDICT_FILE: DICT_DIR / version["cedict"]["file"],
        }
        for name, data in staged.items():
            _write_gz(tmp_dir / name, data)
            new_paths[name] = tmp_dir / name

        print("Resolving glosses with the current files...", file=sys.stderr)
        before = gloss_audit.build_snapshot(
            DICT_DIR / version["hsk"]["file"], DICT_DIR / version["cedict"]["file"], []
        )
        print("Resolving glosses with the new files...", file=sys.stderr)
        after = gloss_audit.build_snapshot(new_paths[HSK_FILE], new_paths[CEDICT_FILE], [])
        (tmp_dir / "before.json").write_text(json.dumps(before, ensure_ascii=False))
        (tmp_dir / "after.json").write_text(json.dumps(after, ensure_ascii=False))
        diff_argv = ["diff", str(tmp_dir / "before.json"), str(tmp_dir / "after.json")]
        diff_argv += ["--limit", str(args.limit)]
        for lvl in args.level or []:
            diff_argv += ["--level", str(lvl)]
        print()
        gloss_audit.main(diff_argv)

        if args.dry_run:
            print("\nDry run: app/data/dict/ left unchanged.")
            return 0
        for name in staged:
            shutil.move(tmp_dir / name, DICT_DIR / name)

    VERSION_FILE.write_text(
        json.dumps(new_version, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {', '.join(sorted(staged))} and VERSION.json to {DICT_DIR}.")
    print("Next: review the diff above, run pytest (golden set), then commit app/data/dict/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

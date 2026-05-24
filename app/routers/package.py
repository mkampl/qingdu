"""
Pre-analyzed package import (Phase #100).

A package is a JSON file the user produced with their own LLM (or curated
by hand) for specialised corpora. The endpoint validates the structure,
layers in our HSK / radical metadata, runs grammar pattern detection, and
returns the same shape `/api/analyze` does — so the SPA renders the
result through the existing reader pipeline unchanged.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.auth import require_auth
from app.database import User
from app.schemas import QingduPackage
from app.services.package_import import (
    PackageImportError,
    transform,
    validate,
)
from app.services.translation import translation_cache

router = APIRouter(tags=["Package Import"])
logger = logging.getLogger(__name__)

_MAX_PACKAGE_BYTES = 5 * 1024 * 1024  # 5 MB ceiling — bigger than any real package
_SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "packages"


@router.post("/api/import/package")
async def import_package_body(
    package: QingduPackage,
    strict: bool = Query(True, description="Reject mismatched token concatenation."),
    user: User = Depends(require_auth),
) -> dict:
    """
    JSON-body variant. The auth dependency only gates access — the package
    contents are user-supplied and not stored automatically (the SPA decides
    when to save the result via /api/texts/save).
    """
    _ = user
    return _do_import(package, strict=strict)


@router.post("/api/import/package/file")
async def import_package_file(
    file: UploadFile = File(...),
    strict: bool = Query(True),
    user: User = Depends(require_auth),
) -> dict:
    """
    Multipart variant — the user uploads a .json file. Parses + validates
    + transforms exactly like the body variant.
    """
    _ = user
    raw = await file.read(_MAX_PACKAGE_BYTES + 1)
    if len(raw) > _MAX_PACKAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large — cap is {_MAX_PACKAGE_BYTES // (1024 * 1024)} MB.",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Not valid JSON: {e}") from e
    try:
        package = QingduPackage.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e
    return _do_import(package, strict=strict)


@router.get("/api/import/package/samples")
async def list_sample_packages() -> dict:
    """
    List the bundled reference packages so the SPA can render a
    "Try a sample" affordance on the import tab. Packages ship in
    `app/data/packages/`.
    """
    if not _SAMPLES_DIR.exists():
        return {"samples": []}
    out = []
    for f in sorted(_SAMPLES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append(
            {
                "name": f.stem,
                "title": data.get("title"),
                "source": data.get("source"),
                "byline": data.get("byline"),
                "language_hint": data.get("language_hint"),
                "char_count": len(data.get("text") or ""),
            }
        )
    return {"samples": out}


@router.get("/api/import/package/samples/{name}")
async def get_sample_package(name: str) -> dict:
    """
    Return a bundled sample by name. Names are restricted to the basename
    of the .json file in `app/data/packages/`; we explicitly reject paths.
    """
    # Path traversal guard — name must be a flat slug.
    if "/" in name or ".." in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid sample name.")
    path = _SAMPLES_DIR / f"{name}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Sample {name!r} not found.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"Couldn't read sample: {e}") from e


@router.get("/api/import/package/schema.json")
async def package_schema() -> JSONResponse:
    """
    Serve the JSON Schema for QingduPackage. The author of a package can
    feed this to their LLM (Anthropic / OpenAI structured outputs, etc.)
    to get a reliable round-trip. We auto-generate from the Pydantic
    model so it can't drift from the source of truth.
    """
    schema = QingduPackage.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "QingduPackage"
    return JSONResponse(content=schema)


def _do_import(package: QingduPackage, strict: bool) -> dict:
    try:
        validate(package, strict=strict)
    except PackageImportError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    result = transform(package)

    # Defense-in-depth: also seed the server-side translation cache so even
    # a stale frontend (or a /api/translate hit from a different code path)
    # gets the curated translation back. The primary path is now the
    # `sentence_translations` baked into the analyze response (no TTL).
    for sentence, translation in (package.sentence_translations or {}).items():
        if not sentence or not translation:
            continue
        translation_cache[f"{sentence}_en"] = {
            "translation": translation,
            "source": "package",
        }

    logger.info(
        "Imported package title=%s source=%s tokens=%d sentence_translations=%d",
        package.title,
        package.source,
        len(package.tokens),
        len(package.sentence_translations or {}),
    )
    return {
        "title": package.title,
        "byline": package.byline,
        "source": package.source,
        "content": package.text,
        "analysisData": result,
        "sentence_translations": package.sentence_translations or {},
    }

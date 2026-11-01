"""APP_VERSION (OpenAPI docs) must match the Android versionName."""

import re
from pathlib import Path

from app.core.constants import APP_VERSION

GRADLE = Path(__file__).resolve().parent.parent / "frontend" / "android" / "app" / "build.gradle"


def test_app_version_matches_android_version_name():
    match = re.search(r'versionName\s+"([^"]+)"', GRADLE.read_text(encoding="utf-8"))
    assert match, "versionName not found in build.gradle"
    assert match.group(1) == APP_VERSION

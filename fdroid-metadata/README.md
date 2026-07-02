# F-Droid submission metadata

This directory is for the maintainer's reference only. The actual submission lives in the [fdroiddata](https://gitlab.com/fdroid/fdroiddata) repository.

## Files

- `at.itvoodoo.qingdu.yml` — the metadata YAML to drop into `fdroiddata/metadata/`.

## Submission steps

1. Fork `https://gitlab.com/fdroid/fdroiddata`.
2. Copy `at.itvoodoo.qingdu.yml` into `fdroiddata/metadata/`.
3. Run `fdroid lint at.itvoodoo.qingdu` from the fdroiddata root to catch syntax issues.
4. Run `fdroid build at.itvoodoo.qingdu:44 --on-server --no-tarball` to confirm the build is reproducible.
5. Open a merge request titled `New app: at.itvoodoo.qingdu (QingDu)` with a short description and a link to the GitHub release.

Reviewers will check:
- Source is fully free (MIT)
- No bundled non-free libraries (verified — see `THIRD_PARTY_LICENSES.md`)
- No analytics SDKs / trackers (verified — no Firebase, no Google Analytics, no proprietary SDKs)
- Bundle doesn't ship with closed binaries (verified — Capacitor + Vue 3 only)
- Build is reproducible (verify locally before submitting)
- Anti-feature claims are accurate (NonFreeNet declared)

## What's in the APK

The Android APK is a Capacitor wrapper bundling the Vite-built SPA (`frontend/dist/`). It does NOT ship:
- the Python backend
- the SUBTLEX-CH frequency file (`app/data/subtlex_char_pinyin_freq.json`)
- any other server-side data

These live on the server only. F-Droid evaluation is about the APK, not the server, so SUBTLEX-CH's licensing (see THIRD_PARTY_LICENSES.md — free academic download, not the NC-ND we'd previously assumed) is not a concern for F-Droid distribution either way.

## Anti-Features

- **NonFreeNet** — the app depends on a server for its core function. Disclosed; not a blocker for inclusion. See `at.itvoodoo.qingdu.yml`.

## Versioning convention

`versionCode` is `versionName` × 100 + patch when there's a patch:
- 1.0.42 → 43
- 1.0.43 → 44

The fastlane changelog under `frontend/android/fastlane/metadata/android/en-US/changelogs/<versionCode>.txt` is what F-Droid pulls into the listing.

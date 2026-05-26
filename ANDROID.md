# Android wrapper

The Android app is a [Capacitor](https://capacitorjs.com/) shell around the Vue 3 SPA. The same web UI runs unchanged inside a Chromium WebView; backend calls go out over HTTPS to whatever instance of QingDu you point it at (the default points at the production deployment).

## Prerequisites

- Node 20+
- Android SDK + platform tools (via Android Studio is easiest)
- JDK 17 (matches the Capacitor 7 Android target)

## Building a debug APK

```bash
cd frontend
npm install
VITE_API_BASE_URL=https://qingdu.itvoodoo.at npm run build
npx cap sync android
cd android
./gradlew assembleDebug
```

The unsigned debug APK lands at:

```
frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

`adb install` it on a connected device, or open the Android Studio project at `frontend/android/` to run on the emulator.

## After a web release

The SPA build is bundled into the APK at `cap sync` time. If you want a fresh APK to pick up the latest backend-side features that need new SPA assets:

```bash
cd frontend
VITE_API_BASE_URL=https://qingdu.itvoodoo.at npm run build
npx cap sync android
cd android
./gradlew assembleDebug
```

For server-only fixes (no SPA changes) no native rebuild is needed — the WebView fetches the live backend on next launch.

## Permissions

- `INTERNET` — backend traffic.
- `RECORD_AUDIO` + `MODIFY_AUDIO_SETTINGS` — pronunciation check via the in-WebView MediaRecorder.

## Project layout

- `frontend/capacitor.config.ts` — appId, scheme, asset directory.
- `frontend/android/` — generated Gradle project (committed for reproducible builds).
- `frontend/android/app/src/main/AndroidManifest.xml` — permissions + activity wiring.
- `frontend/android/fastlane/metadata/android/en-US/` — store-listing copy that can feed F-Droid / Play Console.

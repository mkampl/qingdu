# Android wrapper

The Android app is a [Capacitor](https://capacitorjs.com/) shell around the Vue 3 SPA. The same web UI runs unchanged inside a Chromium WebView; backend calls go out over HTTPS to whatever instance of QingDu you point it at (the default is the production deployment at <https://qingdu.itvoodoo.at>).

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

Adb-push it to a connected device or open the Android Studio project at `frontend/android/` to run on the emulator.

## Building a release AAB

For Play Store / F-Droid distribution, build a signed Android App Bundle:

```bash
cd frontend/android
./gradlew bundleRelease
```

Output:

```
frontend/android/app/build/outputs/bundle/release/app-release.aab
```

The release build needs a keystore. Generate one once:

```bash
keytool -genkey -v -keystore qingdu-release.keystore \
    -alias qingdu -keyalg RSA -keysize 2048 -validity 10000
```

Then add the credentials to `android/keystore.properties` (gitignored):

```
storeFile=/abs/path/to/qingdu-release.keystore
storePassword=…
keyAlias=qingdu
keyPassword=…
```

…and wire it into `android/app/build.gradle` per the [Capacitor signing guide](https://capacitorjs.com/docs/android/deploying-to-google-play#signing-your-app).

## Targets

### F-Droid

Open-source distribution; no developer fee. The store listing draws from `frontend/android/fastlane/metadata/android/en-US/`:

- `title.txt`
- `short_description.txt`
- `full_description.txt`
- `changelogs/{versionCode}.txt`
- `images/icon.png`, `images/featureGraphic.png`, `images/phoneScreenshots/*.png`

Submission is a PR against [fdroiddata](https://gitlab.com/fdroid/fdroiddata) with a metadata YAML pointing at this repo's git tags. Volunteer review takes weeks.

### Play Store

One-time $25 developer fee at <https://play.google.com/console/>. Upload the signed `.aab` from `bundleRelease`. Reuse the same `fastlane/metadata/` files for the store listing — Play Console accepts the fastlane structure.

## Updating the wrapper after a web release

The SPA build is bundled into the APK at `cap sync` time. After every web release that needs to ship through the native app:

```bash
cd frontend
VITE_API_BASE_URL=https://qingdu.itvoodoo.at npm run build
npx cap sync android
# bump android/app/build.gradle versionCode + versionName
# add a fastlane/metadata/.../changelogs/{versionCode}.txt
./gradlew bundleRelease
```

For tweaks that don't change the SPA (server-only fixes), no native rebuild is needed — the WebView fetches the latest backend on next launch.

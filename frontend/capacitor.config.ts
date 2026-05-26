import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Capacitor configuration for the QingDu Android wrapper.
 *
 * Build flow:
 *   1. `VITE_API_BASE_URL=https://qingdu.itvoodoo.at npm run build`
 *      compiles the SPA with absolute API URLs baked in.
 *   2. `npx cap sync android` copies `dist/` into the Android project
 *      under `android/app/src/main/assets/public`.
 *   3. Open the Android Studio project at `frontend/android/` to build
 *      a signed AAB/APK, or run `./gradlew bundleRelease` from there.
 *
 * Distribution targets in order: F-Droid (open source, no fee), then
 * Play Store. The same AAB works for both — F-Droid prefers a
 * reproducible build from a git tag (see fastlane/metadata/).
 */
const config: CapacitorConfig = {
  // F-Droid / Play Store identifier — reverse-DNS, deterministic.
  appId: "at.itvoodoo.qingdu",
  appName: "QingDu",
  // The Vite build directory; `cap sync` reads from here.
  webDir: "dist",
  android: {
    // https-scheme assets so MediaRecorder + getUserMedia + Web Speech
    // and any other permission-gated browser APIs work the same as on
    // the production web app. Mixed-content not allowed by default —
    // every API call must reach the backend over HTTPS too (the
    // VITE_API_BASE_URL set at build time should be https://...).
    allowMixedContent: false,
  },
  // Lock the WebView to the bundled assets — never load a different
  // origin (e.g. an attacker-controlled http URL). Backend traffic
  // still goes out via fetch() to the configured base URL.
  server: {
    androidScheme: "https",
  },
};

export default config;

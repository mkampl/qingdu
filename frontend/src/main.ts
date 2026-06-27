import { createApp } from "vue";
import { createPinia } from "pinia";
import { Capacitor } from "@capacitor/core";

// Self-hosted Latin variable fonts. CJK fonts come from Google Fonts on the
// web (loaded lazily below) so we get their on-demand glyph subsetting; on
// native (Capacitor / F-Droid APK) we skip the CDN entirely and let the
// device's CJK font handle it. PingFang SC ships with iOS, Noto Sans SC
// has been the Android default since 7+, Source Han Serif SC is the common
// fallback on Linux.
import "@fontsource-variable/inter";
// Newsreader: import both upright and italic axes — the editorial italic
// (used in the empty state, sentence-translation card, and reader title)
// needs the true italic shapes, not a synthesised oblique.
import "@fontsource-variable/newsreader";
import "@fontsource-variable/newsreader/wght-italic.css";

import App from "./App.vue";
import { router } from "./router";
import "./styles/global.css";

// Web-only CJK font load. Native builds (Capacitor) skip this so the F-Droid
// APK never makes an external Google Fonts request.
if (!Capacitor.isNativePlatform()) {
  const cjkFamilies = [
    "Noto+Serif+SC:wght@300;400;500;600;700",
    "Noto+Sans+SC:wght@400;500;600",
  ];
  for (const family of cjkFamilies) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = `https://fonts.googleapis.com/css2?family=${family}&display=swap`;
    document.head.appendChild(link);
  }
}

const app = createApp(App);
app.use(createPinia());
app.use(router);

// Capacitor's WebView surfaces every uncaught JS error as
// `[object Object]` / `[object DOMException]` through logcat, which
// hides the actual cause when the app is running in the Android
// wrapper. Reformat unhandled errors + promise rejections so logcat
// gets `name: message` strings instead.
function describe(err: unknown): string {
  if (err instanceof Error) {
    const name = err.name || "Error";
    return `${name}: ${err.message}`;
  }
  return String(err);
}
app.config.errorHandler = (err, _vm, info) => {
  // eslint-disable-next-line no-console
  console.error(`[vue] ${describe(err)} — ${info}`);
};
window.addEventListener("error", (e) => {
  // eslint-disable-next-line no-console
  console.error(`[window.onerror] ${describe(e.error ?? e.message)}`);
});
window.addEventListener("unhandledrejection", (e) => {
  // eslint-disable-next-line no-console
  console.error(`[unhandledrejection] ${describe(e.reason)}`);
});

app.mount("#app");

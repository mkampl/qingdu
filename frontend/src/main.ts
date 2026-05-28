import { createApp } from "vue";
import { createPinia } from "pinia";

// Self-hosted Latin variable fonts. CJK fonts come from Google Fonts (see
// global.css) because their subsetting infrastructure ships only the glyphs
// actually needed for the page, which a static self-host can't replicate.
import "@fontsource-variable/inter";
// Newsreader: import both upright and italic axes — the editorial italic
// (used in the empty state, sentence-translation card, and reader title)
// needs the true italic shapes, not a synthesised oblique.
import "@fontsource-variable/newsreader";
import "@fontsource-variable/newsreader/wght-italic.css";

import App from "./App.vue";
import { router } from "./router";
import "./styles/global.css";

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

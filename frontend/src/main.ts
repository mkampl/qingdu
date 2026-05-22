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
app.mount("#app");

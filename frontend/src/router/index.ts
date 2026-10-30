import { createRouter, createWebHistory } from "vue-router";

// No scrollBehavior here: this app's html/body/#app are pinned to the
// viewport height and <main id="app-scroll"> scrolls internally instead
// (see src/utils/scroll.ts) — window itself never scrolls, so Vue
// Router's window-scroll-based scrollBehavior would be a silent no-op.
// App.vue's router hooks handle scroll on navigation.
export const router = createRouter({
  history: createWebHistory("/"),
  routes: [
    {
      path: "/",
      name: "reader",
      component: () => import("@/views/ReaderView.vue"),
    },
    {
      path: "/texts",
      name: "texts",
      component: () => import("@/views/SavedTextsView.vue"),
    },
    {
      path: "/vocab",
      name: "vocab-index",
      component: () => import("@/views/VocabView.vue"),
    },
    // Path-style links to the Vocab tabs, which use ?tab=…. Without these
    // /vocab/:id below catches them as a list id.
    { path: "/vocab/browse", redirect: { name: "vocab-index", query: { tab: "browse" } } },
    { path: "/vocab/lists", redirect: { name: "vocab-index", query: { tab: "lists" } } },
    {
      path: "/discover",
      name: "discover",
      component: () => import("@/views/DiscoverView.vue"),
    },
    {
      path: "/library",
      name: "library",
      component: () => import("@/views/LibraryView.vue"),
    },
    {
      path: "/words",
      name: "words",
      component: () => import("@/views/WordsView.vue"),
    },
    {
      path: "/review",
      name: "review",
      component: () => import("@/views/ReviewView.vue"),
    },
    {
      path: "/welcome",
      name: "welcome",
      component: () => import("@/views/WelcomeView.vue"),
    },
    {
      path: "/grammar",
      name: "grammar",
      component: () => import("@/views/GrammarView.vue"),
    },
    {
      path: "/grammar/:id",
      name: "grammar-pattern",
      component: () => import("@/views/GrammarPatternView.vue"),
    },
    {
      path: "/tones",
      name: "tones",
      component: () => import("@/views/ToneDrillView.vue"),
    },
    {
      path: "/vocab/:id",
      name: "vocab",
      component: () => import("@/views/VocabListView.vue"),
      props: true,
    },
    {
      path: "/admin",
      name: "admin",
      component: () => import("@/views/AdminView.vue"),
    },
    {
      path: "/s/:token",
      name: "share",
      component: () => import("@/views/PublicShareView.vue"),
      props: true,
    },
    {
      // Prototype, deliberately not linked from the nav.
      path: "/watch",
      name: "watch",
      component: () => import("@/views/WatchView.vue"),
    },
    {
      path: "/privacy",
      name: "privacy",
      component: () => import("@/views/PrivacyView.vue"),
    },
    {
      path: "/impressum",
      name: "impressum",
      component: () => import("@/views/ImpressumView.vue"),
    },
  ],
});

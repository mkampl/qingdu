import { createRouter, createWebHistory } from "vue-router";

export const router = createRouter({
  history: createWebHistory("/"),
  // Without this, navigating to a new page inherits whatever scrollY the
  // previous page was left at (e.g. opening a text from partway down the
  // Library list lands the reader scrolled down too). Saved-progress
  // restoration in ReaderView.restoreScroll runs after this, on nextTick.
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition ?? { top: 0 };
  },
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
    // Path-style deep links — older docs / external links promised
    // /vocab/browse and /vocab/lists, but the Vocab view uses ?tab=…
    // query strings instead. Without these the strings get caught by
    // /vocab/:id below and render "we couldn't find that list".
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

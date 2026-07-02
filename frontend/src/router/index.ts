import { createRouter, createWebHistory } from "vue-router";

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
  ],
});

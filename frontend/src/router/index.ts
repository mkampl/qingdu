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
      component: () => import("@/views/VocabListsView.vue"),
    },
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
  ],
});

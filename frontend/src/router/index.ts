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
  ],
});

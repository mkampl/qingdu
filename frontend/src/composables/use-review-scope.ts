import { computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useOpenLibraryText } from "@/composables/use-open-library-text";
import { useOpenSavedText } from "@/composables/use-open-saved-text";
import { useReviewStore } from "@/stores/review";

/**
 * /review?text=<text key> or ?list=<id> focuses the session on one text's
 * pre-learned words or one vocab list (stores/review scope). A session on
 * a text's words leads back to that text ("saved:<id>" or
 * "library:<slug>"; a pasted text has no place to go).
 */
export function useReviewScope() {
  const review = useReviewStore();
  const router = useRouter();
  const route = useRoute();
  const openSavedText = useOpenSavedText();
  const openLibraryText = useOpenLibraryText();

  watch(
    () => [route.query.text, route.query.list] as const,
    ([text, list]) => {
      const listId = Number(list);
      void review.setScope(
        typeof text === "string" && text
          ? { textKey: text }
          : typeof list === "string" && Number.isInteger(listId)
            ? { listId }
            : null,
      );
    },
    { immediate: true },
  );

  function clearScope() {
    void router.replace({ path: "/review" });
  }

  const scopeText = computed<{ savedId: number } | { slug: string } | null>(() => {
    const m = /^(saved|library):(.+)$/.exec(review.scope?.textKey ?? "");
    if (!m) return null;
    const id = Number(m[2]);
    if (m[1] === "saved") return Number.isInteger(id) ? { savedId: id } : null;
    return { slug: m[2] };
  });
  const canGoBack = computed(() => scopeText.value !== null);

  async function backToText() {
    const to = scopeText.value;
    if (!to) return;
    const opened =
      "savedId" in to ? await openSavedText(to.savedId) : await openLibraryText(to.slug);
    if (opened) review.reset();
  }

  return { canGoBack, clearScope, backToText };
}

import { ref } from "vue";

/**
 * Inline two-step delete for rows of a list: the first click arms a row
 * (`pendingId`), the confirm button runs `remove`. One delete at a time
 * (`deletingId`), so a slow network can't send it twice; the row is
 * disarmed once it finishes, failed or not. `remove` reports its own
 * success or error.
 */
export function useInlineDelete<T extends { id: number }>(remove: (item: T) => Promise<void>) {
  const pendingId = ref<number | null>(null);
  const deletingId = ref<number | null>(null);

  async function confirmDelete(item: T) {
    if (deletingId.value !== null) return;
    deletingId.value = item.id;
    try {
      await remove(item);
    } finally {
      deletingId.value = null;
      pendingId.value = null;
    }
  }

  return { pendingId, deletingId, confirmDelete };
}

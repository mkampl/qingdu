import { ref, toValue, type MaybeRefOrGetter } from "vue";

import type { ReviewGrade } from "@/api/client";

/**
 * The countdown after a writing quiz: `schedule(g)` fires `onFire(g)` after
 * `delayMs` (0 = off). `pending` is the grade waiting to fire, for the
 * countdown bar on its button. `cancel()` stops it (a grade click, a tap
 * on the card, a new card).
 */
export function useAutoGrade(
  delayMs: MaybeRefOrGetter<number>,
  onFire: (g: ReviewGrade) => void,
) {
  const pending = ref<ReviewGrade | null>(null);
  let timer: number | null = null;

  function cancel() {
    if (timer !== null) {
      window.clearTimeout(timer);
      timer = null;
    }
    pending.value = null;
  }

  function schedule(g: ReviewGrade) {
    cancel();
    const ms = toValue(delayMs);
    if (ms <= 0) return;
    pending.value = g;
    timer = window.setTimeout(() => {
      timer = null;
      pending.value = null;
      onFire(g);
    }, ms);
  }

  return { pending, schedule, cancel };
}

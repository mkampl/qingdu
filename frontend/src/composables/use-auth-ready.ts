import { watch } from "vue";

import { useAuthStore } from "@/stores/auth";

/**
 * Run `onAuthed` once the boot-time session check has settled and the user
 * is signed in — immediately if that is already the case, otherwise as soon
 * as it happens (hydration finishing on a hard reload, or a later login).
 * `onSignedOut` runs when the settled state is anonymous, including after
 * a logout, so views can drop their per-user data.
 *
 * Replaces the per-view `onMounted(load)` + `if (!auth.isAuthed) return`
 * pattern, which raced App.vue's async auth.hydrate() on deep links.
 */
export function onAuthReady(onAuthed: () => void, onSignedOut?: () => void) {
  const auth = useAuthStore();
  watch(
    () => (auth.hydrated ? (auth.user?.username ?? "") : null),
    (who) => {
      if (who === null) return;
      if (who) onAuthed();
      else onSignedOut?.();
    },
    { immediate: true },
  );
}

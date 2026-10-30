import { forgetUserCaches } from "@/services/notifications";
import { useAnalysisStore } from "@/stores/analysis";
import { useAudioPlayerStore } from "@/stores/audio-player";
import { useReaderStore } from "@/stores/reader";
import { useReviewStore } from "@/stores/review";
import { useTextFoldersStore } from "@/stores/text-folders";
import { useUserWordsStore } from "@/stores/userWords";
import { useVocabListsStore } from "@/stores/vocab-lists";

/**
 * Reset every store that holds data belonging to the signed-in account, so
 * the next account on the same device never sees the previous one's word
 * states, lists, review stats or saved text.
 *
 * `keepReading` leaves the reader (current analysis, saved-text id, audio
 * queue, the folder a save goes to) alone. Used when a session merely
 * expires: the same person most likely signs straight back in and
 * shouldn't lose the page. If a *different* account signs in afterwards,
 * the auth store resets the reader then.
 *
 * Add new per-user stores here — this is the one place logout clears.
 */
export function resetUserScopedStores(options: { keepReading?: boolean } = {}) {
  useUserWordsStore().reset();
  useReviewStore().resetAll();
  useVocabListsStore().clear();
  // Reminder caches (due count, streak) are per account;
  // they are rewritten on the next review-stats refresh.
  forgetUserCaches();
  if (!options.keepReading) {
    useAnalysisStore().reset();
    useReaderStore().reset();
    useAudioPlayerStore().reset();
    useTextFoldersStore().reset();
  }
}

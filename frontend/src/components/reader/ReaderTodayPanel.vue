<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";

import * as api from "@/api/client";
import type { LibraryForYouItem } from "@/api/client";
import type { AnalysisResponse, SavedTextSummary } from "@/api/types";
import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useReaderStore } from "@/stores/reader";
import { useReviewStore } from "@/stores/review";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";
import { normalizeProgress, parseTags } from "@/utils/saved-text";

const auth = useAuthStore();
const userWords = useUserWordsStore();
const review = useReviewStore();
const analysis = useAnalysisStore();
const reader = useReaderStore();
const toasts = useToastStore();
const router = useRouter();

const recentText = ref<SavedTextSummary | null>(null);
const pick = ref<LibraryForYouItem | null>(null);
const loading = ref(true);
const openingSlug = ref<string | null>(null);
const openingTextId = ref<number | null>(null);

let fetched = false;
async function fetchTodayHooks() {
  if (fetched || !auth.isAuthed) return;
  fetched = true;
  loading.value = true;
  try {
    const [texts, forYou] = await Promise.all([
      api.listTexts().catch(() => [] as SavedTextSummary[]),
      api
        .libraryForYou({ limit: 5 })
        .catch(() => ({ items: [] as LibraryForYouItem[] })),
    ]);

    // "Continue reading" = most-recent saved text that's mid-read
    // (0 < progress < 1). Falls back to the most recent saved text overall
    // so a returning user always sees the entry-point — useful even if
    // they never tracked progress in the first place.
    const inProgress = texts.filter(
      (t) => t.reading_progress > 0 && t.reading_progress < 1,
    );
    recentText.value = inProgress[0] ?? texts[0] ?? null;

    // First item — backend already sorted by comprehension score.
    pick.value = forYou.items?.[0] ?? null;
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  // Try immediately — covers the "auth already hydrated" path. Also
  // watch auth.isAuthed so we re-fire once hydrate finishes if we
  // were premature on mount (the auth store hydrates async on App.vue
  // boot; ReaderTodayPanel is in the Reader route which can render
  // before that completes).
  if (auth.isAuthed) {
    void fetchTodayHooks();
  } else {
    loading.value = false;
  }
});
watch(
  () => auth.isAuthed,
  (next) => {
    if (next) void fetchTodayHooks();
    else {
      // Logged out: clear the panel.
      fetched = false;
      recentText.value = null;
      pick.value = null;
      loading.value = false;
    }
  },
);

const reviewDue = computed(() => review.dueNow);
const streak = computed(() => userWords.stats.streak);

const anyHook = computed(
  () =>
    reviewDue.value > 0 ||
    recentText.value !== null ||
    pick.value !== null ||
    streak.value > 0,
);

function progressPct(t: SavedTextSummary): number {
  return Math.round(normalizeProgress(t.reading_progress) * 100);
}

function scorePct(item: LibraryForYouItem): number {
  return Math.round(
    Math.max(0, Math.min(1, item.comprehension_score ?? 0)) * 100,
  );
}

function openSavedText(text: SavedTextSummary) {
  // Mirrors SavedTextsView.open — hydrate the analysis store with the saved
  // data and stay on / so the reader picks it up without a re-analyse trip.
  openingTextId.value = text.id;
  analysis.loadSaved(text.content, text.analysisData, {
    id: text.id,
    progress: normalizeProgress(text.reading_progress),
    title: text.title ?? "",
    tags: parseTags(text.tags),
    glossaryListIds: text.glossary_list_ids,
  });
  reader.reset();
  // The Today panel sits inside ReaderView itself; we're already on / so a
  // router.push("/") is a no-op. The store change drives the swap.
}

async function openLibraryPick(slug: string) {
  openingSlug.value = slug;
  try {
    const entry = await api.getLibraryEntry(slug);
    analysis.loadSaved(entry.text, entry.analyzed as AnalysisResponse, null);
    reader.reset();
    void router.push("/");
  } catch (e) {
    toasts.error(e instanceof Error ? e.message : "Couldn't open that text");
  } finally {
    openingSlug.value = null;
  }
}
</script>

<template>
  <!-- Reader landing for authed users. Surfaces the three actionable hooks
       the app's expanded scope has — overdue review queue, the last text
       you didn't finish, and a level-matched library pick — so the home
       route isn't just "paste a paragraph" anymore. The italic paste
       prompt still lives below this panel for anyone who actually arrived
       to read fresh text. -->
  <div
    v-if="anyHook && !loading"
    class="space-y-3 border-t border-border-subtle pt-10"
  >
    <span
      class="font-display text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
    >
      Today
    </span>

    <!-- Highest-priority CTA: due reviews. Coral accent so it reads as
         the primary action when present. -->
    <RouterLink
      v-if="reviewDue > 0"
      to="/review"
      class="group flex items-baseline justify-between gap-3 rounded-lg border border-accent/40 bg-accent/5 px-4 py-3 transition-colors hover:bg-accent/10"
    >
      <span class="flex items-baseline gap-2">
        <span class="font-display text-xl font-medium tabular-nums text-accent">
          {{ reviewDue }}
        </span>
        <span class="font-display text-sm text-fg">
          {{ reviewDue === 1 ? "card due" : "cards due" }}
        </span>
      </span>
      <span class="font-mono text-[10px] uppercase tracking-wider text-fg-muted group-hover:text-fg">
        Review →
      </span>
    </RouterLink>

    <!-- Continue reading. One click puts the user back into a text they
         already started — saves the trip through /texts and a scan. -->
    <button
      v-if="recentText"
      type="button"
      :disabled="openingTextId !== null"
      class="group flex w-full items-baseline justify-between gap-3 rounded-lg border border-border-subtle bg-bg-elevated px-4 py-3 text-left transition-colors hover:border-border hover:bg-bg-sunken disabled:opacity-60"
      @click="openSavedText(recentText)"
    >
      <span class="min-w-0 flex-1">
        <span class="block font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
          Continue reading
        </span>
        <span class="block truncate font-cn-serif text-base text-fg">
          {{ recentText.title }}
        </span>
      </span>
      <span
        v-if="recentText.reading_progress > 0"
        class="shrink-0 font-mono text-[10px] tabular-nums text-fg-muted group-hover:text-fg"
      >
        {{ progressPct(recentText) }}%
      </span>
    </button>

    <!-- Today's pick from the library, comprehension-matched. -->
    <button
      v-if="pick"
      type="button"
      :disabled="openingSlug !== null"
      class="group flex w-full items-baseline justify-between gap-3 rounded-lg border border-border-subtle bg-bg-elevated px-4 py-3 text-left transition-colors hover:border-border hover:bg-bg-sunken disabled:opacity-60"
      @click="openLibraryPick(pick.slug)"
    >
      <span class="min-w-0 flex-1">
        <span class="block font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
          From the library
        </span>
        <span class="block truncate font-cn-serif text-base text-fg">
          {{ pick.title }}
        </span>
      </span>
      <span class="shrink-0 font-mono text-[10px] tabular-nums text-fg-muted group-hover:text-fg">
        {{ scorePct(pick) }}% known
      </span>
    </button>

    <!-- Streak hint — non-action, lives last so it never crowds the CTAs.
         Hidden when streak is 0 so we don't demoralise a fresh user. -->
    <p
      v-if="streak > 0"
      class="pt-2 font-display text-xs italic text-fg-muted"
    >
      {{ streak }}-day streak — come back tomorrow to keep it going.
    </p>
  </div>
</template>

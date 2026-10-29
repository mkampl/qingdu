<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import * as api from "@/api/client";
import type { HskBrowseItem, UserWordState } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useSettingsStore } from "@/stores/settings";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";
import {
  BROWSE_STATES,
  browseEmptyText,
  browseLevels,
  browseStateCount,
  mapBrowseLevel,
  parseBrowseState,
  shiftBrowseCounts,
  type BrowseState,
  type BrowseStateCounts,
} from "@/utils/browse";

import HskChip from "@/components/reader/HskChip.vue";
import { effectiveWordState } from "@/components/reader/utils";

const auth = useAuthStore();
const authModals = useAuthModalsStore();
const settings = useSettingsStore();
const toasts = useToastStore();
const userWords = useUserWordsStore();
// Optional: the view also renders without a router (unit tests).
const route = useRoute() as ReturnType<typeof useRoute> | undefined;
const router = useRouter() as ReturnType<typeof useRouter> | undefined;

// Levels follow the HSK version picked in Settings (old HSK: 1–6).
const levels = computed(() => browseLevels(settings.hskVersion));

const PAGE = 60;

// Level and state live in the URL (?tab=browse&level=new-3&state=known),
// so a filtered view survives reloads and the back button.
function initialLevel(): string {
  const raw = route?.query.level;
  const v = Array.isArray(raw) ? raw[0] : raw;
  if (typeof v === "string" && (v === "all" || /^(new|old)-\d$/.test(v))) {
    return mapBrowseLevel(v, settings.hskVersion);
  }
  return mapBrowseLevel("new-1", settings.hskVersion);
}

const level = ref<string>(initialLevel());
const stateFilter = ref<BrowseState>(parseBrowseState(route?.query.state));
const stateCounts = ref<BrowseStateCounts | null>(null);
const search = ref("");
const items = ref<HskBrowseItem[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);
const busy = ref<string | null>(null);

watch(
  () => settings.hskVersion,
  (v) => {
    level.value = mapBrowseLevel(level.value, v);
  },
);

// Debounce search input so we don't fire on every keystroke.
let searchTimer: number | undefined;
watch(search, () => {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => void load(true), 300);
});

watch([level, stateFilter], () => {
  void load(true);
  if (!router || !route) return;
  const query = { ...route.query, level: level.value, state: stateFilter.value };
  if (stateFilter.value === "all") delete (query as Record<string, unknown>).state;
  void router.replace({ query });
});

// Every load gets a number; only the newest one may touch the list. A
// "load more" still in flight when the level or search changes would
// otherwise append the old level's rows to the new one.
let loadSeq = 0;

async function load(reset = false) {
  const seq = ++loadSeq;
  if (reset) {
    items.value = [];
    total.value = 0;
    stateCounts.value = null;
  }
  const offset = items.value.length;
  loading.value = true;
  error.value = null;
  try {
    const params: Parameters<typeof api.browseHsk>[0] = {
      offset,
      limit: PAGE,
    };
    if (level.value !== "all") params.level = level.value;
    if (search.value.trim()) params.q = search.value.trim();
    if (stateFilter.value !== "all" && auth.isAuthed) params.state = stateFilter.value;
    const r = await api.browseHsk(params);
    if (seq !== loadSeq) return;
    items.value = reset ? r.items : [...items.value, ...r.items];
    total.value = r.total;
    if (r.state_counts) stateCounts.value = r.state_counts;
  } catch (e) {
    if (seq !== loadSeq) return;
    error.value = e instanceof Error ? e.message : "Couldn't load HSK vocabulary.";
  } finally {
    if (seq === loadSeq) loading.value = false;
  }
}

const hasMore = computed(() => items.value.length < total.value);
const emptyText = computed(() =>
  browseEmptyText(level.value, search.value, stateFilter.value),
);

function stateOf(item: HskBrowseItem): UserWordState | null {
  return effectiveWordState(
    userWords.stateOf(item.hanzi),
    userWords.hydrated,
    item.user_state,
  );
}

const STATE_DONE: Record<UserWordState, string> = {
  learning: "Added {w} to learning.",
  known: "Marked {w} as known.",
  ignored: "Ignoring {w}.",
};

/**
 * Set a state. Clicking the active "Ignored" un-ignores the word; the
 * active Learning / Known buttons do nothing — clearing those would drop
 * the word's review history, which belongs on /words, not a browse list.
 */
async function toggleState(item: HskBrowseItem, state: UserWordState) {
  if (!auth.isAuthed) {
    authModals.openLogin();
    return;
  }
  const current = stateOf(item);
  if (current === state && state !== "ignored") return;
  busy.value = item.hanzi;
  const from = current ?? "new";
  try {
    if (current === state) {
      await userWords.clearState(item.hanzi);
      item.user_state = null;
      if (stateCounts.value) stateCounts.value = shiftBrowseCounts(stateCounts.value, from, "new");
    } else {
      await userWords.setState(item.hanzi, state);
      if (stateCounts.value) stateCounts.value = shiftBrowseCounts(stateCounts.value, from, state);
      // Keep the row in step for the pre-hydration fallback.
      item.user_state = state;
      toasts.success(STATE_DONE[state].replace("{w}", item.hanzi));
    }
  } catch (e) {
    toasts.error(e instanceof Error ? e.message : `Couldn't update ${item.hanzi}.`);
  } finally {
    busy.value = null;
  }
}

const ACTIONS: { state: UserWordState; label: string; active: string }[] = [
  { state: "learning", label: "Learn", active: "Learning" },
  { state: "known", label: "Known", active: "Known" },
  { state: "ignored", label: "Ignore", active: "Ignored" },
];

function actionTitle(item: HskBrowseItem, state: UserWordState): string {
  const current = stateOf(item);
  if (current === state) {
    return state === "ignored"
      ? "Stop ignoring"
      : state === "learning"
        ? "In your learning pool"
        : "Marked as known";
  }
  return state === "learning"
    ? "Add to learning"
    : state === "known"
      ? "Mark as known"
      : "Ignore this word";
}

onMounted(() => void load(true));
</script>

<template>
  <section class="space-y-5">
    <p class="text-sm text-fg-muted leading-relaxed">
      Browse the full HSK vocabulary by level or search any hanzi / pinyin /
      meaning. Add a word to learning and it shows up in the next review
      session; mark the ones you already know or want to skip.
    </p>

    <p
      v-if="auth.hydrated && !auth.isAuthed"
      class="rounded-md border border-border-subtle bg-bg-sunken px-3 py-2 text-xs text-fg-muted"
    >
      <button
        type="button"
        class="font-medium text-accent hover:underline"
        @click="authModals.openLogin()"
      >
        Sign in
      </button>
      to add words to learning or mark them known.
    </p>

    <!-- Level filter — one horizontally scrolling row. -->
    <div
      role="tablist"
      aria-label="HSK level"
      class="-mx-4 overflow-x-auto px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      <div class="flex w-max gap-1.5">
        <button
          v-for="lv in levels"
          :key="lv.key"
          type="button"
          role="tab"
          :aria-selected="level === lv.key"
          class="inline-flex items-center gap-1 rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors"
          :class="
            level === lv.key
              ? 'border-accent bg-accent/10 text-accent'
              : 'border-border-subtle bg-bg-elevated text-fg-muted hover:border-border hover:text-fg'
          "
          @click="level = lv.key"
        >
          {{ lv.label }}
        </button>
      </div>
    </div>

    <!-- Search -->
    <input
      v-model="search"
      type="search"
      aria-label="Search HSK vocabulary"
      placeholder="Search hanzi, pinyin, or meaning"
      class="w-full rounded-md border border-border-subtle bg-bg px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
    />

    <!-- State filter — "which HSK 3 words do I know?". Counts follow the
         level and search above; only meaningful when signed in. -->
    <div
      v-if="auth.isAuthed"
      role="group"
      aria-label="Filter by word state"
      class="flex flex-wrap items-center gap-1.5"
    >
      <button
        v-for="st in BROWSE_STATES"
        :key="st.key"
        type="button"
        :aria-pressed="stateFilter === st.key"
        class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors"
        :class="
          stateFilter === st.key
            ? 'border-accent bg-accent/10 text-accent'
            : 'border-border-subtle bg-bg-elevated text-fg-muted hover:border-border hover:text-fg'
        "
        @click="stateFilter = st.key"
      >
        {{ st.label }}
        <span
          v-if="browseStateCount(stateCounts, st.key) !== null"
          class="tabular-nums opacity-70"
        >{{ browseStateCount(stateCounts, st.key) }}</span>
      </button>
    </div>

    <p
      v-if="!loading && items.length === 0 && !error"
      class="py-10 text-center font-display italic text-fg-muted"
    >
      {{ emptyText }}
    </p>

    <p v-if="error" class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">
      {{ error }}
    </p>

    <!-- Result rows: hanzi, pinyin + meaning, state actions; wraps on
         narrow screens. -->

    <ul class="space-y-2">
      <li
        v-for="item in items"
        :key="item.hanzi"
        class="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-lg border border-border-subtle bg-bg-elevated px-3 py-2.5"
      >
        <span class="font-cn text-lg text-fg">{{ item.hanzi }}</span>
        <span class="font-mono text-xs text-fg-muted">{{ item.pinyin }}</span>
        <span class="min-w-0 flex-1 truncate text-sm text-fg-muted">
          {{ item.meaning }}
        </span>
        <HskChip
          v-if="item.level_new || item.level_old"
          :level="
            settings.hskVersion === 'old'
              ? (item.level_old ?? item.level_new)
              : (item.level_new ?? item.level_old)
          "
          size="xs"
        />
        <div
          class="flex shrink-0 items-center gap-1"
          role="group"
          :aria-label="`State of ${item.hanzi}`"
        >
          <button
            v-for="a in ACTIONS"
            :key="a.state"
            type="button"
            :disabled="!auth.isAuthed || busy === item.hanzi"
            :aria-pressed="stateOf(item) === a.state"
            :title="auth.isAuthed ? actionTitle(item, a.state) : 'Sign in to track words'"
            class="inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-50"
            :class="
              stateOf(item) === a.state
                ? 'border-accent bg-accent/15 text-accent'
                : 'border-border-subtle bg-bg-elevated text-fg-muted hover:border-border hover:text-fg'
            "
            @click="toggleState(item, a.state)"
          >
            {{ stateOf(item) === a.state ? a.active : a.label }}
          </button>
        </div>
      </li>
    </ul>

    <!-- Pager -->
    <div v-if="loading && items.length > 0" class="py-4 text-center text-xs text-fg-subtle">
      Loading…
    </div>
    <div v-if="loading && items.length === 0" class="py-10 text-center text-xs text-fg-subtle">
      Loading HSK vocabulary…
    </div>
    <button
      v-if="hasMore && !loading"
      type="button"
      class="w-full rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
      @click="load()"
    >
      Load {{ Math.min(PAGE, total - items.length) }} more · {{ items.length }} / {{ total }}
    </button>
  </section>
</template>

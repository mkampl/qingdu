<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import * as api from "@/api/client";
import type { HskBrowseItem } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";

import HskChip from "@/components/reader/HskChip.vue";

const auth = useAuthStore();
const toasts = useToastStore();
const userWords = useUserWordsStore();

type LevelKey = "all" | "new-1" | "new-2" | "new-3" | "new-4" | "new-5" | "new-6" | "new-7" | "new-8" | "new-9";

const LEVELS: { key: LevelKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "new-1", label: "HSK 1" },
  { key: "new-2", label: "HSK 2" },
  { key: "new-3", label: "HSK 3" },
  { key: "new-4", label: "HSK 4" },
  { key: "new-5", label: "HSK 5" },
  { key: "new-6", label: "HSK 6" },
  { key: "new-7", label: "HSK 7" },
  { key: "new-8", label: "HSK 8" },
  { key: "new-9", label: "HSK 9" },
];

const PAGE = 60;

const level = ref<LevelKey>("new-1");
const search = ref("");
const items = ref<HskBrowseItem[]>([]);
const total = ref(0);
const offset = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);
const adding = ref<string | null>(null);

// Debounce search input so we don't fire on every keystroke.
let searchTimer: number | undefined;
watch(search, () => {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => void load(true), 300);
});

watch(level, () => void load(true));

async function load(reset = false) {
  if (reset) {
    offset.value = 0;
    items.value = [];
  }
  loading.value = true;
  error.value = null;
  try {
    const params: Parameters<typeof api.browseHsk>[0] = {
      offset: offset.value,
      limit: PAGE,
    };
    if (level.value !== "all") params.level = level.value;
    if (search.value.trim()) params.q = search.value.trim();
    const r = await api.browseHsk(params);
    if (reset) {
      items.value = r.items;
    } else {
      items.value = [...items.value, ...r.items];
    }
    total.value = r.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Couldn't load HSK vocabulary.";
  } finally {
    loading.value = false;
  }
}

async function loadMore() {
  offset.value += PAGE;
  await load(false);
}

const hasMore = computed(() => items.value.length < total.value);

async function addToLearning(item: HskBrowseItem) {
  if (!auth.isAuthed) {
    toasts.error("Sign in to track words.");
    return;
  }
  adding.value = item.hanzi;
  try {
    await userWords.setState(item.hanzi, "learning");
    // Patch the row optimistically so the button label flips immediately
    // without a refetch of the whole page.
    item.user_state = "learning";
    toasts.success(`Added ${item.hanzi} to learning.`);
  } catch (e) {
    toasts.error(
      e instanceof Error ? e.message : `Couldn't add ${item.hanzi}.`,
    );
  } finally {
    adding.value = null;
  }
}

function stateLabel(item: HskBrowseItem): string {
  switch (item.user_state) {
    case "learning":
      return "Learning";
    case "known":
      return "Known";
    case "ignored":
      return "Ignored";
    default:
      return "Add to learning";
  }
}

onMounted(() => void load(true));
</script>

<template>
  <section class="space-y-5">
    <p class="text-sm text-fg-muted leading-relaxed">
      Browse the full HSK vocabulary by level or search any hanzi / pinyin /
      meaning. Tap a word to add it to your learning pool — it'll show up in
      the next review session.
    </p>

    <!-- Level filter — snap-scroll on mobile so 10 chips don't wrap into
         a wall. Same pattern Library uses. -->
    <div
      role="tablist"
      aria-label="HSK level"
      class="-mx-4 overflow-x-auto px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      <div class="flex w-max gap-1.5">
        <button
          v-for="lv in LEVELS"
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
      placeholder="Search hanzi, pinyin, or meaning"
      class="w-full rounded-md border border-border-subtle bg-bg px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
    />

    <p
      v-if="!loading && items.length === 0 && !error"
      class="py-10 text-center font-display italic text-fg-muted"
    >
      No matches in this level.
    </p>

    <p v-if="error" class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">
      {{ error }}
    </p>

    <!-- Result list — flexible row layout that wraps gracefully on narrow
         screens. The hanzi anchor on the left, pinyin + meaning in the
         middle, action button on the right. -->
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
          :level="item.level_new ?? item.level_old"
          size="xs"
        />
        <button
          type="button"
          :disabled="adding === item.hanzi || item.user_state !== null"
          class="inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider transition-colors"
          :class="
            item.user_state === null
              ? 'border border-accent/40 bg-accent/10 text-accent hover:bg-accent/20'
              : 'border border-border-subtle bg-bg-sunken text-fg-subtle'
          "
          @click="addToLearning(item)"
        >
          <span v-if="adding === item.hanzi" class="inline-block size-2.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
          <span v-else>{{ stateLabel(item) }}</span>
        </button>
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
      @click="loadMore"
    >
      Load {{ Math.min(PAGE, total - items.length) }} more · {{ items.length }} / {{ total }}
    </button>
  </section>
</template>

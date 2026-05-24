<script setup lang="ts">
/**
 * "Resources"-style glossary picker. Sits next to the Import button on
 * the reader's input rail. Lists every vocab-list the user has flagged
 * `apply_as_glossary`, lets them toggle each on/off per text.
 *
 * Selection lives in the analysis store as `glossaryListIds`:
 *   null   = use all glossary-flagged lists (the default for fresh text)
 *   []     = explicitly use none
 *   [3,5]  = use only these two
 *
 * Hidden entirely when the user hasn't flagged any lists yet — there's
 * nothing to pick and we don't want to advertise the feature in a way
 * the user can't act on.
 */
import { computed, onMounted, ref, watch } from "vue";

import { useAnalysisStore } from "@/stores/analysis";
import { useVocabListsStore } from "@/stores/vocab-lists";

const analysis = useAnalysisStore();
const vocabLists = useVocabListsStore();
const open = ref(false);
const containerRef = ref<HTMLElement | null>(null);

onMounted(() => {
  void vocabLists.ensureLoaded();
});

const glossaryLists = computed(() =>
  vocabLists.lists.filter((vl) => vl.apply_as_glossary),
);

const hasAny = computed(() => glossaryLists.value.length > 0);

/** Which glossary IDs are *effectively* active right now. */
const activeIds = computed<Set<number>>(() => {
  const ids = analysis.glossaryListIds;
  // null = use all flagged lists -> reflect that as "every checkbox ticked".
  if (ids === null) {
    return new Set(glossaryLists.value.map((vl) => vl.id));
  }
  return new Set(ids);
});

const activeCount = computed(() => activeIds.value.size);

function toggleList(id: number) {
  const next = new Set(activeIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  applySelection(next);
}

function selectAll() {
  applySelection(new Set(glossaryLists.value.map((vl) => vl.id)));
}

function selectNone() {
  applySelection(new Set());
}

function applySelection(selected: Set<number>) {
  const all = glossaryLists.value.map((vl) => vl.id);
  // Canonicalise: "every flagged list" -> null (so future-added glossaries
  // are picked up automatically); otherwise an explicit array.
  if (selected.size === all.length && all.every((id) => selected.has(id))) {
    analysis.glossaryListIds = null;
  } else {
    analysis.glossaryListIds = Array.from(selected).sort((a, b) => a - b);
  }
  // If there's a text in the box already analysed, the change should
  // take effect — re-run analysis so meanings update in place.
  if (analysis.hasResult && analysis.inputText) {
    void analysis.analyze(analysis.inputText);
  }
}

function close() {
  open.value = false;
}

function onDocClick(e: MouseEvent) {
  if (!open.value) return;
  const target = e.target as Node;
  if (containerRef.value && !containerRef.value.contains(target)) close();
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape" && open.value) close();
}

watch(open, (isOpen) => {
  if (typeof document === "undefined") return;
  if (isOpen) {
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKey);
  } else {
    document.removeEventListener("click", onDocClick);
    document.removeEventListener("keydown", onKey);
  }
});
</script>

<template>
  <div v-if="hasAny" ref="containerRef" class="relative">
    <button
      type="button"
      class="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-fg-muted transition-colors hover:text-fg hover:bg-bg-sunken"
      :class="{ 'bg-bg-sunken text-fg': open }"
      :title="`${activeCount} of ${glossaryLists.length} glossaries active`"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click.stop="open = !open"
    >
      <svg
        width="11"
        height="11"
        viewBox="0 0 11 11"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M1.5 1.5h7v8h-7zM3 3.5h4M3 5.5h4M3 7.5h3"
          stroke="currentColor"
          stroke-width="1.4"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      Glossaries
      <span
        v-if="activeCount > 0"
        class="rounded-full px-1.5 py-0 font-mono text-[9px] tabular-nums"
        :style="{
          backgroundColor: 'color-mix(in oklch, var(--color-glossary), transparent 80%)',
          color: 'var(--color-glossary)',
        }"
      >
        {{ activeCount }}
      </span>
    </button>

    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        role="menu"
        class="absolute bottom-full right-0 z-30 mb-2 w-72 rounded-lg border border-border bg-bg-elevated p-3 shadow-lg ring-1 ring-border-subtle"
      >
        <div class="mb-2 flex items-baseline justify-between gap-2">
          <p
            class="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
          >
            Apply to this text
          </p>
          <div class="flex gap-1 font-mono text-[9px] uppercase tracking-wider">
            <button
              type="button"
              class="text-fg-subtle transition-colors hover:text-fg"
              @click="selectAll"
            >
              All
            </button>
            <span class="text-fg-subtle">·</span>
            <button
              type="button"
              class="text-fg-subtle transition-colors hover:text-fg"
              @click="selectNone"
            >
              None
            </button>
          </div>
        </div>

        <ul class="max-h-56 space-y-1 overflow-y-auto">
          <li v-for="vl in glossaryLists" :key="vl.id">
            <label
              class="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-bg-sunken"
            >
              <input
                type="checkbox"
                :checked="activeIds.has(vl.id)"
                class="accent-accent"
                @change="toggleList(vl.id)"
              />
              <span class="flex-1 truncate text-fg">{{ vl.name }}</span>
              <span
                class="font-mono text-[10px] text-fg-subtle tabular-nums"
              >
                {{
                  vl.sections
                    ? vl.sections.reduce(
                        (sum, s) => sum + (s.words?.length ?? 0),
                        0,
                      )
                    : 0
                }} words
              </span>
            </label>
          </li>
        </ul>

        <p
          class="mt-2 border-t border-border-subtle pt-2 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
        >
          Glossary words override HSK meanings.
        </p>
      </div>
    </Transition>
  </div>
</template>

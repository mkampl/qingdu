<script setup lang="ts">
/**
 * Sidebar panel listing the grammar patterns detected in the current text.
 *
 * Each pattern is a collapsible row. Tap to expand the explanation +
 * example, and to surface a "Jump to first use" button that scrolls the
 * reader to the matching span and pulses it briefly.
 *
 * Hidden entirely when the analysis carries no `grammar` payload (older
 * saved texts pre-Phase D) or no matches were found.
 */
import { computed, nextTick, ref } from "vue";

import type { GrammarPayload } from "@/api/types";

const props = defineProps<{ grammar: GrammarPayload | undefined }>();

const expandedId = ref<string | null>(null);
const collapsed = ref(false);

const patternsWithCounts = computed(() => {
  if (!props.grammar) return [];
  const counts = new Map<string, number>();
  for (const m of props.grammar.matches) {
    counts.set(m.pattern_id, (counts.get(m.pattern_id) ?? 0) + 1);
  }
  return props.grammar.patterns.map((p) => ({
    ...p,
    count: counts.get(p.id) ?? 0,
  }));
});

function toggle(id: string) {
  expandedId.value = expandedId.value === id ? null : id;
}

async function jumpToFirstMatch(patternId: string) {
  if (!props.grammar) return;
  const match = props.grammar.matches.find((m) => m.pattern_id === patternId);
  if (!match) return;
  await nextTick();
  // Reader words are rendered with `data-word-idx` (see ReadingText.vue
  // — we add the attribute as part of Phase D so this lookup works).
  const el = document.querySelector(
    `[data-word-idx="${match.start_word_idx}"]`,
  ) as HTMLElement | null;
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  // Pulse so the user can find the span after the scroll.
  const span = el.closest(".sentence") ?? el;
  span.classList.add("grammar-pulse");
  setTimeout(() => span.classList.remove("grammar-pulse"), 1800);
}
</script>

<template>
  <section v-if="grammar && grammar.patterns.length" class="space-y-3">
    <header
      class="flex items-baseline justify-between gap-2 border-b border-border-subtle pb-2"
    >
      <h2
        class="font-display text-[11px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
      >
        Grammar
      </h2>
      <button
        type="button"
        class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle transition-colors hover:text-fg"
        :aria-expanded="!collapsed"
        @click="collapsed = !collapsed"
      >
        {{ collapsed ? `show (${grammar.patterns.length})` : "hide" }}
      </button>
    </header>

    <ul v-if="!collapsed" class="space-y-1.5">
      <li
        v-for="p in patternsWithCounts"
        :key="p.id"
        class="rounded-md border border-border-subtle bg-bg-elevated transition-colors"
        :class="{ 'border-accent': expandedId === p.id }"
      >
        <button
          type="button"
          class="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
          :aria-expanded="expandedId === p.id"
          @click="toggle(p.id)"
        >
          <div class="min-w-0 flex-1">
            <p class="font-cn-serif text-base text-fg">{{ p.title }}</p>
            <p
              class="mt-0.5 truncate font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
            >
              {{ p.pinyin }} · HSK {{ p.hsk_level }}
              <span v-if="p.count > 1"> · ×{{ p.count }}</span>
            </p>
          </div>
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            fill="none"
            class="shrink-0 text-fg-subtle transition-transform"
            :class="{ 'rotate-90': expandedId === p.id }"
            aria-hidden="true"
          >
            <path
              d="M3.5 2l3 3-3 3"
              stroke="currentColor"
              stroke-width="1.4"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </button>

        <div v-if="expandedId === p.id" class="border-t border-border-subtle px-3 py-3">
          <p class="text-xs leading-relaxed text-fg">{{ p.explanation }}</p>
          <div
            class="mt-2.5 rounded-md bg-bg-sunken/60 px-3 py-2 font-cn-serif text-sm text-fg"
          >
            {{ p.example }}
          </div>
          <p class="mt-1 text-[11px] italic text-fg-muted">
            {{ p.example_translation }}
          </p>
          <button
            type="button"
            class="mt-3 inline-flex items-center gap-1 rounded-full border border-border bg-bg-elevated px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
            @click="jumpToFirstMatch(p.id)"
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
              <path
                d="M2 5h6M5 2l3 3-3 3"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            Jump to first use
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>

<style>
/* The pulse runs on the .sentence ancestor of the matched span so the
   highlight wraps the whole construction, not just the trigger token. */
.grammar-pulse {
  animation: grammar-pulse 1.6s ease-out;
}
@keyframes grammar-pulse {
  0% {
    background-color: var(--color-accent);
    border-radius: 0.375rem;
  }
  100% {
    background-color: transparent;
    border-radius: 0.375rem;
  }
}
</style>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";

import type { Section } from "./utils";

const props = defineProps<{
  sections: Section[];
  /** The article element wrapping the reading text — used to scope the
   *  IntersectionObserver search to just our section anchors. */
  articleEl: HTMLElement | null;
}>();

/**
 * Key of the section the user is currently reading. Updated by an
 * IntersectionObserver watching all section <h2 id="sec-N">…</h2> headings.
 * We pick "current" as the topmost section whose anchor has scrolled into
 * the upper half of the viewport — that matches the intuitive "this is the
 * part I'm reading right now" mental model rather than "the next heading
 * the user will hit".
 */
const currentKey = ref<string | null>(null);

let observer: IntersectionObserver | null = null;

function attach() {
  observer?.disconnect();
  if (!props.articleEl || props.sections.length === 0) {
    currentKey.value = null;
    return;
  }
  const anchors = Array.from(
    props.articleEl.querySelectorAll<HTMLElement>(".reader-section-anchor"),
  );
  if (!anchors.length) {
    currentKey.value = null;
    return;
  }
  if (!currentKey.value) currentKey.value = props.sections[0]?.key ?? null;

  // Single observer for all anchors. The rootMargin of "-15% 0px -75% 0px"
  // creates a thin horizontal band roughly 15% from the top of the viewport;
  // a heading entering that band becomes "current". This avoids the
  // dual-state thrashing you get when two anchors are visible at once.
  observer = new IntersectionObserver(
    (entries) => {
      // Update from the entry with the highest top intersection ratio.
      for (const entry of entries) {
        if (entry.isIntersecting) {
          const key = (entry.target as HTMLElement).dataset.sectionKey;
          if (key) currentKey.value = key;
        }
      }
    },
    {
      rootMargin: "-15% 0px -75% 0px",
      threshold: 0,
    },
  );
  for (const a of anchors) observer.observe(a);
}

// Re-attach when sections change (new analysis) or the article element
// reference changes (initial mount, fresh load).
watch(
  () => [props.sections, props.articleEl],
  () => {
    // Defer one tick so DOM has the new anchors before we attach.
    requestAnimationFrame(attach);
  },
  { immediate: true },
);

onBeforeUnmount(() => observer?.disconnect());

function jumpTo(section: Section) {
  if (!props.articleEl) return;
  const el = props.articleEl.querySelector<HTMLElement>(`#${CSS.escape(section.key)}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  // Immediately reflect the click — the observer will catch up on scroll-end,
  // but updating now feels snappier.
  currentKey.value = section.key;
}
</script>

<template>
  <nav v-if="sections.length" aria-label="In this text">
    <p
      class="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
    >
      In this text
    </p>
    <ol class="space-y-0.5 border-l border-border-subtle">
      <li v-for="(section, idx) in sections" :key="section.key">
        <button
          type="button"
          class="-ml-px block w-full border-l-2 py-1 pl-3 pr-2 text-left text-[12px] leading-snug transition-colors"
          :class="
            currentKey === section.key
              ? 'border-accent text-fg font-medium'
              : 'border-transparent text-fg-muted hover:text-fg hover:border-border'
          "
          @click="jumpTo(section)"
        >
          <span
            class="mr-1 inline-block w-4 text-right font-mono text-[10px] text-fg-subtle"
          >
            {{ idx + 1 }}
          </span>
          <span class="text-cn-serif">{{ section.title }}</span>
        </button>
      </li>
    </ol>
  </nav>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, toRef, watch } from "vue";

import { appScrollEl } from "@/utils/scroll";

import ChopMark from "./ChopMark.vue";

const props = defineProps<{
  /** Element to track scroll progress within. */
  target: HTMLElement | null;
}>();

const emit = defineEmits<{
  /** Fires whenever the computed scroll-progress fraction (0..1) changes. */
  (e: "progress", value: number): void;
}>();

const progress = ref(0);
const everCompleted = ref(false);

function compute() {
  const el = props.target;
  if (!el) {
    if (progress.value !== 0) {
      progress.value = 0;
      emit("progress", 0);
    }
    return;
  }
  const scrollEl = appScrollEl();
  const rect = el.getBoundingClientRect();
  const viewportH = scrollEl.clientHeight;
  // Position of the article's top edge relative to the scroll container's
  // own top (not the browser viewport's — the fixed header above <main>
  // would otherwise throw this off by its height).
  const start = rect.top - scrollEl.getBoundingClientRect().top;
  const total = rect.height;
  let next: number;
  if (total <= viewportH) {
    next = start < 0 ? 1 : 0;
  } else {
    // 0 when the top of the article is at the top of the viewport,
    // 1 when the bottom of the article is at the bottom of the viewport.
    const scrolled = -start;
    const maxScroll = total - viewportH;
    next = Math.max(0, Math.min(1, scrolled / maxScroll));
  }
  if (next !== progress.value) {
    progress.value = next;
    emit("progress", next);
  }
  // Once the reader reaches the end of a text, the chop stays stamped — even
  // if they scroll back up — until the article changes.
  if (progress.value >= 0.99) everCompleted.value = true;
}

onMounted(() => {
  compute();
  // The scroll fires on <main>, not window — see utils/scroll.ts. Resize
  // stays on window; that's a real window-level event either way, and it
  // also covers main's clientHeight changing as a side effect.
  appScrollEl().addEventListener("scroll", compute, { passive: true });
  window.addEventListener("resize", compute);
});
onBeforeUnmount(() => {
  appScrollEl().removeEventListener("scroll", compute);
  window.removeEventListener("resize", compute);
});

// Reset the "ever completed" flag when the target element changes — i.e. when
// the user analyses a new text and ReaderView swaps the article ref.
watch(toRef(props, "target"), () => {
  everCompleted.value = false;
  compute();
});

defineExpose({ recompute: compute });
</script>

<template>
  <div
    class="pointer-events-none relative hidden h-full w-px bg-border-subtle md:block"
    aria-hidden="true"
  >
    <div
      class="origin-top bg-accent transition-[height] duration-150 ease-out"
      :style="{
        width: '1px',
        height: `${progress * 100}%`,
      }"
    />
    <!-- Completion chop — appears at the bottom of the spine when the reader
         finishes the text, then stays. Stamp-settle animation reuses the chop
         keyframes from global.css via the ChopMark `settled` prop. -->
    <Transition
      enter-active-class="transition duration-500 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
    >
      <div
        v-if="everCompleted"
        class="absolute -left-[15px] -bottom-1 flex items-center justify-center"
      >
        <ChopMark :size="22" :settled="true" />
      </div>
    </Transition>
  </div>
</template>

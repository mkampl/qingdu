<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, toRef, watch } from "vue";

import ChopMark from "./ChopMark.vue";

const props = defineProps<{
  /** Element to track scroll progress within. */
  target: HTMLElement | null;
}>();

const progress = ref(0);
const everCompleted = ref(false);

function compute() {
  const el = props.target;
  if (!el) {
    progress.value = 0;
    return;
  }
  const rect = el.getBoundingClientRect();
  const viewportH = window.innerHeight;
  const start = rect.top;
  const total = rect.height;
  if (total <= viewportH) {
    progress.value = start < 0 ? 1 : 0;
  } else {
    // 0 when the top of the article is at the top of the viewport,
    // 1 when the bottom of the article is at the bottom of the viewport.
    const scrolled = -start;
    const maxScroll = total - viewportH;
    progress.value = Math.max(0, Math.min(1, scrolled / maxScroll));
  }
  // Once the reader reaches the end of a text, the chop stays stamped — even
  // if they scroll back up — until the article changes.
  if (progress.value >= 0.99) everCompleted.value = true;
}

onMounted(() => {
  compute();
  window.addEventListener("scroll", compute, { passive: true });
  window.addEventListener("resize", compute);
});
onBeforeUnmount(() => {
  window.removeEventListener("scroll", compute);
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

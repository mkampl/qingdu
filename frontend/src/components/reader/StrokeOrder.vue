<script setup lang="ts">
/**
 * Animated stroke-order viewer for one or more hanzi.
 *
 * hanzi-writer is lazy-imported the first time this component mounts —
 * keeps the main bundle slim for users who never open the accordion.
 * Character data is fetched on demand from the package's CDN.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{ chars: string }>();

const cjkChars = computed(() =>
  Array.from(props.chars || "").filter((c) => /[一-鿿]/.test(c)),
);

const activeIdx = ref(0);
const containerRef = ref<HTMLDivElement | null>(null);

// Hold the live HanziWriter instance so we can replay / destroy it.
type AnyHanziWriter = { animateCharacter: () => void } | null;
const writer = ref<AnyHanziWriter>(null);
const loading = ref(false);
const error = ref<string | null>(null);

async function ensureWriterFor(idx: number) {
  if (!cjkChars.value[idx] || !containerRef.value) return;
  loading.value = true;
  error.value = null;
  try {
    // Dynamic import so hanzi-writer stays out of the main bundle.
    const HanziWriter = (await import("hanzi-writer")).default;
    // Wipe whatever was there for the previous character.
    containerRef.value.innerHTML = "";
    const w = HanziWriter.create(containerRef.value, cjkChars.value[idx], {
      width: 140,
      height: 140,
      padding: 6,
      strokeAnimationSpeed: 1,
      delayBetweenStrokes: 90,
      showOutline: true,
      strokeColor: "#1f2937", // resolved from --color-fg at light theme; OK for both via opacity
    });
    writer.value = w;
    w.animateCharacter();
  } catch (e) {
    error.value =
      e instanceof Error ? e.message : "Couldn't load stroke data.";
  } finally {
    loading.value = false;
  }
}

function replay() {
  if (writer.value) writer.value.animateCharacter();
}

function setActive(idx: number) {
  activeIdx.value = idx;
}

onMounted(() => {
  if (cjkChars.value.length) {
    void ensureWriterFor(0);
  }
});

watch(activeIdx, (idx) => {
  void ensureWriterFor(idx);
});

watch(
  () => props.chars,
  () => {
    activeIdx.value = 0;
    if (cjkChars.value.length) void ensureWriterFor(0);
  },
);

onBeforeUnmount(() => {
  // hanzi-writer doesn't expose an explicit destroy, but nuking the
  // container DOM ensures its requestAnimationFrame loop GCs cleanly.
  if (containerRef.value) containerRef.value.innerHTML = "";
});
</script>

<template>
  <div v-if="cjkChars.length" class="space-y-2">
    <!-- Multi-char picker. Single-char words skip this row. -->
    <div v-if="cjkChars.length > 1" class="flex flex-wrap items-center gap-1">
      <button
        v-for="(ch, i) in cjkChars"
        :key="i"
        type="button"
        class="rounded-md border px-2 py-1 font-cn-serif text-base transition-colors"
        :class="
          activeIdx === i
            ? 'border-accent bg-bg-sunken text-fg'
            : 'border-border-subtle text-fg-muted hover:border-accent hover:text-fg'
        "
        @click="setActive(i)"
      >
        {{ ch }}
      </button>
    </div>

    <div class="flex items-center gap-3">
      <div
        ref="containerRef"
        class="rounded-md border border-border-subtle bg-bg-elevated"
        style="width: 140px; height: 140px;"
        aria-label="Stroke-order animation"
      />
      <div class="flex flex-col gap-2 text-xs">
        <button
          type="button"
          class="rounded-md border border-border bg-bg-elevated px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:opacity-50"
          :disabled="loading"
          @click="replay"
        >
          Replay
        </button>
        <p v-if="error" class="text-[11px] text-red-700 dark:text-red-300">
          {{ error }}
        </p>
        <p v-else-if="loading" class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
          Loading…
        </p>
        <p v-else class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
          Tap a character on the left for multi-char words.
        </p>
      </div>
    </div>
  </div>
</template>

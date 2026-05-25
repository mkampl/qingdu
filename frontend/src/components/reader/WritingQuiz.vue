<script setup lang="ts">
/**
 * hanzi-writer quiz card for Phase #94 review mode.
 *
 * The user is shown the pinyin + meaning of a word and has to draw each
 * character correctly on the canvas. hanzi-writer tracks per-stroke
 * accuracy + direction; we count total mistakes across all characters
 * and emit `complete` so ReviewView can derive a suggested FSRS grade.
 *
 * Multi-character words run sequentially. The user can "Show stroke"
 * to get a hint (counts as a mistake — same as hanzi-writer's default).
 */
import { computed, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps<{
  /** The whole word string. Non-CJK chars are filtered out. */
  word: string;
  /** Pinyin shown above the canvas as the prompt. */
  pinyin?: string;
  /** Meaning shown above the canvas. */
  meaning?: string;
}>();

const emit = defineEmits<{
  /**
   * Fires once the user has finished drawing every character in the
   * word (or skipped each one). totalMistakes is summed across chars;
   * ReviewView turns this into a suggested grade.
   */
  (e: "complete", payload: { totalMistakes: number; skipped: boolean }): void;
}>();

const cjkChars = computed(() =>
  Array.from(props.word || "").filter((c) => /[一-鿿]/.test(c)),
);

const canvasRef = ref<HTMLDivElement | null>(null);
const currentIdx = ref(0);
const totalMistakes = ref(0);
const currentMistakes = ref(0);
const completed = ref(false);
const skipped = ref(false);
const loading = ref(false);
const error = ref<string | null>(null);

// Hold the active hanzi-writer instance so we can call .hideCharacter()
// for the hint button and tear it down between chars.
type AnyHanziWriter = {
  quiz: (opts: Record<string, unknown>) => void;
  cancelQuiz: () => void;
  animateStroke: (n: number) => void;
} | null;
const writer = ref<AnyHanziWriter>(null);

const isLastChar = computed(
  () => currentIdx.value === cjkChars.value.length - 1,
);

async function startCharQuiz(idx: number) {
  if (!cjkChars.value[idx] || !canvasRef.value) return;
  loading.value = true;
  error.value = null;
  currentMistakes.value = 0;
  try {
    const HanziWriter = (await import("hanzi-writer")).default;
    canvasRef.value.innerHTML = "";
    const w = HanziWriter.create(canvasRef.value, cjkChars.value[idx], {
      width: 200,
      height: 200,
      padding: 8,
      showCharacter: false,
      showOutline: true,
      strokeAnimationSpeed: 1,
      drawingWidth: 32,
      strokeColor: "#1f2937",
      highlightColor: "#10b981", // green for correct
      drawingColor: "#1f2937",
    });
    w.quiz({
      onMistake: (info: { totalMistakes: number }) => {
        currentMistakes.value = info.totalMistakes;
      },
      onCorrectStroke: (info: { totalMistakes: number }) => {
        currentMistakes.value = info.totalMistakes;
      },
      onComplete: (info: { totalMistakes: number }) => {
        // hanzi-writer's totalMistakes is per-character; roll up.
        totalMistakes.value += info.totalMistakes;
        if (isLastChar.value) {
          completed.value = true;
          emit("complete", {
            totalMistakes: totalMistakes.value,
            skipped: false,
          });
        } else {
          currentIdx.value += 1;
        }
      },
    });
    writer.value = w;
  } catch (e) {
    error.value =
      e instanceof Error ? e.message : "Couldn't load stroke data.";
  } finally {
    loading.value = false;
  }
}

function skipCurrentChar() {
  // Treat as if the user got every stroke wrong — adds a heavy
  // mistake penalty to nudge the FSRS grade toward Again.
  totalMistakes.value += 5;
  if (isLastChar.value) {
    completed.value = true;
    skipped.value = true;
    emit("complete", {
      totalMistakes: totalMistakes.value,
      skipped: true,
    });
  } else {
    currentIdx.value += 1;
  }
}

watch(currentIdx, (idx) => {
  void startCharQuiz(idx);
});

watch(
  () => props.word,
  () => {
    currentIdx.value = 0;
    totalMistakes.value = 0;
    currentMistakes.value = 0;
    completed.value = false;
    skipped.value = false;
    void startCharQuiz(0);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  try {
    writer.value?.cancelQuiz();
  } catch {
    /* ignore */
  }
  if (canvasRef.value) canvasRef.value.innerHTML = "";
});
</script>

<template>
  <div class="space-y-3">
    <!-- Prompt row -->
    <div class="text-center">
      <p
        v-if="cjkChars.length > 1"
        class="mb-1 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
      >
        Character {{ currentIdx + 1 }} of {{ cjkChars.length }}
      </p>
      <p class="font-display text-base text-fg-muted">{{ pinyin }}</p>
      <p class="mt-1 font-display text-xl text-fg">{{ meaning }}</p>
    </div>

    <div class="flex justify-center">
      <div
        ref="canvasRef"
        class="rounded-lg border border-border-subtle bg-bg-elevated"
        style="width: 200px; height: 200px;"
        aria-label="Draw the character"
      />
    </div>

    <div class="flex items-center justify-between gap-3 text-xs">
      <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
        Mistakes this char:
        <span class="text-fg tabular-nums">{{ currentMistakes }}</span>
        <span v-if="totalMistakes > currentMistakes" class="text-fg-subtle">
          (total {{ totalMistakes }})
        </span>
      </span>
      <button
        v-if="!completed"
        type="button"
        class="rounded-md border border-border bg-bg-elevated px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:opacity-50"
        :disabled="loading"
        @click="skipCurrentChar"
      >
        {{ isLastChar ? "Skip" : "Skip char" }}
      </button>
    </div>

    <p
      v-if="error"
      class="text-center text-xs text-red-700 dark:text-red-300"
      role="alert"
    >
      {{ error }}
    </p>

    <p
      v-if="loading"
      class="text-center font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
    >
      Loading stroke data…
    </p>
  </div>
</template>

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

/**
 * Bridge for the case where the browser fires PointerEvents but
 * suppresses the legacy MouseEvent compatibility layer (Firefox with
 * strict tracking protection, certain privacy extensions). hanzi-writer
 * v3.7.3 only listens for legacy mouse events, so without this shim
 * pointer-only browsers see no quiz response at all. Skips touch input
 * — touch already fires touchstart/move/end which hanzi-writer handles.
 */
/**
 * hanzi-writer 3.7.3 attaches listeners only for legacy MouseEvent +
 * TouchEvent (node_modules/.../index.esm.js line ~1734). Browsers that
 * suppress those legacy compat events in favour of PointerEvent —
 * Firefox-strict on desktop AND on Android — leave hanzi-writer deaf.
 *
 * Forward all pointer events (mouse and touch) to synthesized
 * MouseEvents. hanzi-writer's mouse handler reads clientX/Y from the
 * MouseEvent, which we copy from the PointerEvent. preventDefault on
 * the PointerEvent suppresses the browser's compat MouseEvent and (per
 * spec on most browsers) also suppresses the synthesized TouchEvent —
 * so hanzi-writer's mouse handler runs exactly once per input.
 */
function forwardPointerAsMouse(e: PointerEvent) {
  const mouseType = (
    {
      pointerdown: "mousedown",
      pointermove: "mousemove",
      pointerup: "mouseup",
    } as Record<string, string>
  )[e.type];
  if (!mouseType) return;
  e.preventDefault();
  const me = new MouseEvent(mouseType, {
    bubbles: true,
    cancelable: true,
    composed: true,
    clientX: e.clientX,
    clientY: e.clientY,
    screenX: e.screenX,
    screenY: e.screenY,
    button: e.button,
    buttons: e.buttons,
    view: window,
  });
  (e.target as Element).dispatchEvent(me);
}

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
  const char = cjkChars.value[idx];
  if (!char || !canvasRef.value) return;
  loading.value = true;
  error.value = null;
  currentMistakes.value = 0;
  try {
    const HanziWriter = (await import("hanzi-writer")).default;

    // Pre-load the character stroke data from the upstream CDN BEFORE
    // wiring quiz mode. Without this, taps in the first second after
    // mount land on a writer that has no data yet and silently no-op,
    // which reads to the user as "nothing happens when I draw".
    const charData = await HanziWriter.loadCharacterData(char);
    if (!charData) {
      error.value = `No stroke data for "${char}".`;
      return;
    }

    canvasRef.value.innerHTML = "";
    const w = HanziWriter.create(canvasRef.value, char, {
      width: 200,
      height: 200,
      showCharacter: false,
      showOutline: true,
      strokeColor: "#1f2937",
      drawingColor: "#1f2937",
      highlightColor: "#10b981",
      drawingFadeDuration: 0,
    });
    w.quiz({
      leniency: 1.5,
      showHintAfterMisses: 3,
      onMistake: (info: { totalMistakes: number }) => {
        currentMistakes.value = info.totalMistakes;
      },
      onCorrectStroke: (info: { totalMistakes: number }) => {
        currentMistakes.value = info.totalMistakes;
      },
      onComplete: (info: { totalMistakes: number }) => {
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

    // PointerEvent → MouseEvent compatibility shim (see helper docstring).
    canvasRef.value.addEventListener(
      "pointerdown",
      forwardPointerAsMouse,
      true,
    );
    canvasRef.value.addEventListener(
      "pointermove",
      forwardPointerAsMouse,
      true,
    );
    canvasRef.value.addEventListener(
      "pointerup",
      forwardPointerAsMouse,
      true,
    );
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
      <!--
        touch-action: none — without this, mobile browsers treat the
          drag inside the SVG as page scroll instead of a draw gesture.
        cursor: crosshair + user-select: none — desktop drag should
          read as drawing, not as text selection.
      -->
      <div
        ref="canvasRef"
        class="rounded-lg border border-border-subtle bg-bg-elevated"
        style="width: 200px; height: 200px; touch-action: none; cursor: crosshair; user-select: none; -webkit-user-select: none;"
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

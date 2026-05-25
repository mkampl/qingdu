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
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { useSettingsStore } from "@/stores/settings";

const settings = useSettingsStore();

const props = withDefaults(
  defineProps<{
    /** The whole word string. Non-CJK chars are filtered out. */
    word: string;
    /** Pinyin shown above the canvas as the prompt. */
    pinyin?: string;
    /** Meaning shown above the canvas. */
    meaning?: string;
    /**
     * Show the faint outline of the character to trace over (helpful for
     * learners). When false, the canvas starts blank and the user has to
     * recall the character from pinyin + meaning alone — closer to an
     * Anki "front-of-card" recall test.
     */
    showOutline?: boolean;
  }>(),
  { showOutline: false },
);

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
 * TouchEvent (node_modules/.../index.esm.js line ~1734).
 *
 * Mobile + tablet input: native TouchEvents fire reliably and reach
 * hanzi-writer's touchstart listener — so we DON'T forward touch
 * pointers. Doing so would synthesize a mousedown AND let the native
 * touchstart fire, causing hanzi-writer's mouse + touch handlers to
 * both run for the same input — which corrupts the quiz state and
 * silently swallows every stroke (verified on user's Firefox Android
 * via /static/hanzi-test.html).
 *
 * Desktop with a privacy mode that suppresses the legacy MouseEvent
 * compat layer (Firefox with strict tracking protection, etc.): the
 * shim translates pointerdown/move/up → mousedown/move/up so
 * hanzi-writer's mouse handler runs exactly once. preventDefault
 * suppresses the browser's would-be compat MouseEvent so we don't
 * double-fire on browsers that do synthesize it.
 */
function forwardPointerAsMouse(e: PointerEvent) {
  if (e.pointerType === "touch") return;
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

// Per-quiz listener bag so multi-char words (and unmount) clean up
// everything we attached to the canvas wrapper. Without this, each
// new char would leak 3 pointer listeners onto the same DOM node,
// firing the shim multiple times per real input and corrupting
// hanzi-writer's stroke state.
let inputListeners: AbortController | null = null;

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

    // Drop any listeners from the previous char in this quiz instance.
    inputListeners?.abort();
    inputListeners = new AbortController();
    const { signal } = inputListeners;

    // The shim MUST be attached BEFORE HanziWriter.create() — that's
    // the order the working /static/hanzi-test.html canvas-2 uses, and
    // we mirror it here verbatim. Attaching after create() left the
    // quiz silently unresponsive on mobile despite identical-looking
    // code.
    canvasRef.value.addEventListener("pointerdown", forwardPointerAsMouse, {
      capture: true,
      signal,
    });
    canvasRef.value.addEventListener("pointermove", forwardPointerAsMouse, {
      capture: true,
      signal,
    });
    canvasRef.value.addEventListener("pointerup", forwardPointerAsMouse, {
      capture: true,
      signal,
    });

    // No-op non-passive touchstart/touchmove listeners. Their only job
    // is to register interest in those events at capture phase with
    // passive: false, which keeps the browser from optimizing the
    // dispatch in a way that hides input from hanzi-writer's bubble-
    // phase touchstart handler. Canvas 2 in the diagnostic page has
    // equivalent listeners (as logging) and works on mobile; without
    // them WritingQuiz.vue did not.
    const noop = () => {};
    canvasRef.value.addEventListener("touchstart", noop, {
      capture: true,
      passive: false,
      signal,
    });
    canvasRef.value.addEventListener("touchmove", noop, {
      capture: true,
      passive: false,
      signal,
    });

    // Theme-aware ink: slate-800 reads cleanly on light backgrounds but
    // disappears against the dark-mode canvas, so flip to slate-200 in
    // dark mode. The settings store's theme value is what drives the
    // `dark` class on <html>, so we read it directly.
    const ink = settings.theme === "dark" ? "#e5e7eb" : "#1f2937";
    const w = HanziWriter.create(canvasRef.value, char, {
      width: 200,
      height: 200,
      showCharacter: false,
      showOutline: props.showOutline,
      strokeColor: ink,
      drawingColor: ink,
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
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Couldn't load stroke data.";
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

// Kick off the very first quiz from onMounted so canvasRef.value is
// guaranteed to be populated. An `immediate: true` watcher would have
// fired synchronously during setup — before mount — and the function's
// `!canvasRef.value` guard would bail silently, which is exactly what
// left the first word of a fresh session unresponsive on mobile.
onMounted(() => void startCharQuiz(0));

// Subsequent word changes (parent advanced to the next card).
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
);

// Re-create the writer when the outline toggle changes mid-card so the
// user can flip it on/off without having to skip to the next word.
watch(
  () => props.showOutline,
  () => {
    if (!completed.value) void startCharQuiz(currentIdx.value);
  },
);

// Same idea for theme: re-create so the ink color picks up the new
// foreground value (slate-200 on dark, slate-800 on light).
watch(
  () => settings.theme,
  () => {
    if (!completed.value) void startCharQuiz(currentIdx.value);
  },
);

onBeforeUnmount(() => {
  inputListeners?.abort();
  inputListeners = null;
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
        Outer frame holds two children, both 200x200 absolutely positioned
        so they overlap:
          1. 米字格 grid as an SVG layer (dashed center cross + diagonals,
             traditional Chinese writing-practice guide). currentColor lets
             dark mode pick it up via Tailwind's text-fg-subtle.
          2. Canvas wrapper where hanzi-writer mounts. Transparent
             background so the grid behind shows through.

        touch-action: none — without this, mobile browsers treat the drag
        inside the SVG as page scroll instead of a draw gesture.
        cursor: crosshair + user-select: none — desktop drag should read
        as drawing, not as text selection.
      -->
      <div
        class="relative rounded-lg border-[3px] border-border bg-bg-elevated"
        style="width: 200px; height: 200px"
      >
        <svg
          class="pointer-events-none absolute inset-0 text-fg-subtle"
          viewBox="0 0 200 200"
          width="200"
          height="200"
          aria-hidden="true"
        >
          <g
            stroke="currentColor"
            stroke-width="1"
            stroke-dasharray="3 4"
            opacity="0.55"
          >
            <line x1="100" y1="0" x2="100" y2="200" />
            <line x1="0" y1="100" x2="200" y2="100" />
            <line x1="0" y1="0" x2="200" y2="200" />
            <line x1="200" y1="0" x2="0" y2="200" />
          </g>
        </svg>
        <div
          ref="canvasRef"
          class="absolute inset-0"
          style="
            touch-action: none;
            cursor: crosshair;
            user-select: none;
            -webkit-user-select: none;
          "
          aria-label="Draw the character"
        />
      </div>
    </div>

    <div class="flex items-center justify-between gap-3 text-xs">
      <span
        class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
      >
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

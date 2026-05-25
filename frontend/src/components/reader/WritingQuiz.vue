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
      drawingFadeDuration: 0, // disable fade so strokes show up immediately
    });
    // Diagnostic logging — temporary, lets us see whether events reach
    // hanzi-writer at all. Strip once Writing mode is confirmed stable.
    // eslint-disable-next-line no-console
    console.log("[WritingQuiz] writer created for", char, w);
    w.quiz({
      leniency: 1.5,
      showHintAfterMisses: 3,
      onMistake: (info: { strokeNum: number; totalMistakes: number }) => {
        // eslint-disable-next-line no-console
        console.log("[WritingQuiz] mistake", info);
        currentMistakes.value = info.totalMistakes;
      },
      onCorrectStroke: (info: { strokeNum: number; totalMistakes: number }) => {
        // eslint-disable-next-line no-console
        console.log("[WritingQuiz] correct stroke", info);
        currentMistakes.value = info.totalMistakes;
      },
      onComplete: (info: { totalMistakes: number }) => {
        // eslint-disable-next-line no-console
        console.log("[WritingQuiz] complete", info);
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

    // Diagnostic probes — every input variant, both capture and bubble
    // phases, plus document-level capture. If we see *any* of these
    // fire when the user clicks the canvas, we know where events ARE
    // going. If none fire, the browser is dropping events entirely on
    // the canvas (likely a Firefox fingerprinting/strict mode quirk).
    const probe = (label: string) => (e: Event) => {
      // eslint-disable-next-line no-console
      console.log(`[WritingQuiz] ${label}`, e.type, {
        target: (e.target as Element)?.tagName,
        currentTarget: (e.currentTarget as Element)?.tagName,
      });
    };
    const events = [
      "pointerdown",
      "pointerup",
      "mousedown",
      "mouseup",
      "click",
      "touchstart",
      "touchend",
    ];
    for (const ev of events) {
      canvasRef.value.addEventListener(ev, probe("canvas:bubble"));
      canvasRef.value.addEventListener(ev, probe("canvas:capture"), true);
    }
    // Also capture document-level — if events fire here but not on the
    // canvas, the canvas itself is invisible to pointer routing.
    const docProbe = (e: Event) => {
      const target = e.target as Element | null;
      if (target?.closest?.('[aria-label="Draw the character"]')) {
        // eslint-disable-next-line no-console
        console.log("[WritingQuiz] document:capture", e.type, target.tagName);
      }
    };
    document.addEventListener("pointerdown", docProbe, true);
    document.addEventListener("mousedown", docProbe, true);
    document.addEventListener("click", docProbe, true);
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

<script setup lang="ts">
/**
 * SRS review session — Phase B.
 *
 * Two modes ship now: Recognition (flashcard) and Dictation (listen-and-type).
 * Cloze is reserved for when the backend can hand back a sample sentence per
 * card; until then the chip is shown with a "soon" badge.
 *
 * Grading flow:
 *   1. user is shown the prompt for the current card
 *   2. user reveals the answer (recognition) or submits it (dictation)
 *   3. user picks Again / Hard / Good / Easy (recognition) — dictation auto-
 *      derives Good from a correct answer, Again from an incorrect one
 *   4. store applies the grade, advances the cursor, optimistic stats tick
 */
import { computed, onMounted, ref, watch } from "vue";

import * as api from "@/api/client";
import type { ReviewGrade, ReviewMode } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useReviewStore } from "@/stores/review";

const review = useReviewStore();
const auth = useAuthStore();

const revealed = ref(false);
const dictationInput = ref("");
const dictationFeedback = ref<"" | "correct" | "wrong">("");
const ttsLoading = ref(false);

const modes: { id: ReviewMode; label: string; hint: string; available: boolean }[] = [
  {
    id: "recognition",
    label: "Recognition",
    hint: "See the character, recall the meaning",
    available: true,
  },
  {
    id: "dictation",
    label: "Dictation",
    hint: "Listen, type what you hear",
    available: true,
  },
  {
    id: "cloze",
    label: "Cloze",
    hint: "Fill the blank in a real sentence — soon",
    available: false,
  },
];

const card = computed(() => review.current);
const total = computed(() => review.queue.length);
const idx = computed(() => Math.min(review.cursor + 1, total.value));

async function start(mode: ReviewMode) {
  if (mode === "cloze") return;
  revealed.value = false;
  dictationInput.value = "";
  dictationFeedback.value = "";
  await review.loadQueue(mode);
}

function reveal() {
  revealed.value = true;
}

async function playTts() {
  if (!card.value) return;
  ttsLoading.value = true;
  try {
    const r = await api.tts(card.value.word);
    if (!r.ok) throw new Error("TTS failed");
    const url = URL.createObjectURL(await r.blob());
    const audio = new Audio(url);
    audio.addEventListener("ended", () => URL.revokeObjectURL(url));
    await audio.play();
  } catch {
    /* keep button responsive */
  } finally {
    ttsLoading.value = false;
  }
}

async function gradeAndAdvance(g: ReviewGrade) {
  if (!card.value) return;
  await review.grade(g);
  // Reset reveal state for the next card.
  revealed.value = false;
  dictationInput.value = "";
  dictationFeedback.value = "";
}

function submitDictation() {
  if (!card.value || dictationFeedback.value !== "") return;
  const guess = dictationInput.value.trim();
  if (!guess) return;
  const target = card.value.word.trim();
  const pinyinTarget = (card.value.pinyin || "").replace(/\s+/g, "").toLowerCase();
  const pinyinNoTones = pinyinTarget.replace(/[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü]/g, (c) => {
    return (
      {
        ā: "a",
        á: "a",
        ǎ: "a",
        à: "a",
        ē: "e",
        é: "e",
        ě: "e",
        è: "e",
        ī: "i",
        í: "i",
        ǐ: "i",
        ì: "i",
        ō: "o",
        ó: "o",
        ǒ: "o",
        ò: "o",
        ū: "u",
        ú: "u",
        ǔ: "u",
        ù: "u",
        ǖ: "u",
        ǘ: "u",
        ǚ: "u",
        ǜ: "u",
        ü: "u",
      }[c] ?? c
    );
  });
  const guessNorm = guess.replace(/\s+/g, "").toLowerCase();
  const correct =
    guess === target || guessNorm === pinyinTarget || guessNorm === pinyinNoTones;
  dictationFeedback.value = correct ? "correct" : "wrong";
}

async function dictationContinue() {
  // Correct → Good (3). Wrong → Again (1). The user can override with the
  // explicit grade row after the answer is revealed.
  await gradeAndAdvance(dictationFeedback.value === "correct" ? 3 : 1);
}

onMounted(() => {
  if (auth.isAuthed) review.refreshStats();
});

// When the user toggles modes mid-session, reset the per-card state.
watch(
  () => review.mode,
  () => {
    revealed.value = false;
    dictationInput.value = "";
    dictationFeedback.value = "";
  },
);
</script>

<template>
  <section class="mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
    <header class="mb-8">
      <p class="font-mono text-[11px] uppercase tracking-[0.22em] text-fg-subtle">
        Spaced repetition
      </p>
      <h1 class="mt-1 font-display text-3xl font-medium tracking-tight text-fg sm:text-4xl">
        Review
      </h1>
      <p class="mt-2 text-sm leading-relaxed text-fg-muted">
        Words you've marked as learning come back here on a schedule —
        sooner if you grade them <em>Again</em>, much later if you grade
        them <em>Easy</em>. Built on FSRS-4.5.
      </p>
    </header>

    <!-- Not authed -->
    <div
      v-if="!auth.isAuthed"
      class="rounded-lg border border-border-subtle bg-bg-elevated px-6 py-10 text-center"
    >
      <p class="font-display text-lg text-fg">Sign in to review your words.</p>
      <p class="mt-2 text-sm text-fg-muted">
        Review draws from words you've marked as
        <span class="font-medium">Learning</span> in the reader.
      </p>
    </div>

    <!-- Stats strip -->
    <div
      v-else
      class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4"
    >
      <div
        v-for="(stat, key) in {
          'Due now': review.stats.due_now,
          'Due today': review.stats.due_today,
          Learning: review.stats.learning,
          'Reviewed today': review.stats.reviewed_today,
        }"
        :key="key"
        class="rounded-lg border border-border-subtle bg-bg-elevated px-4 py-3"
      >
        <p
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          {{ key }}
        </p>
        <p class="mt-1 font-display text-2xl tabular-nums text-fg">
          {{ stat.toLocaleString() }}
        </p>
      </div>
    </div>

    <!-- Mode picker — visible until the user starts a session, then collapses
         into the in-session header. -->
    <div
      v-if="auth.isAuthed && review.queue.length === 0 && !review.loading"
      class="space-y-3"
    >
      <p class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">
        Pick a mode to begin
      </p>
      <div class="grid gap-3 sm:grid-cols-3">
        <button
          v-for="m in modes"
          :key="m.id"
          type="button"
          :disabled="!m.available || review.stats.due_now === 0"
          class="group rounded-lg border border-border-subtle bg-bg-elevated px-5 py-4 text-left transition-colors hover:border-accent hover:bg-bg-sunken disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border-subtle disabled:hover:bg-bg-elevated"
          @click="start(m.id)"
        >
          <div class="flex items-center justify-between">
            <span class="font-display text-lg font-medium text-fg">
              {{ m.label }}
            </span>
            <span
              v-if="!m.available"
              class="font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
            >
              soon
            </span>
          </div>
          <p class="mt-1 text-xs text-fg-muted">{{ m.hint }}</p>
        </button>
      </div>

      <div
        v-if="review.stats.due_now === 0 && review.stats.learning > 0"
        class="mt-6 rounded-lg border border-border-subtle bg-bg-elevated px-5 py-4 text-center text-sm text-fg-muted"
      >
        Nothing's due right now — come back later, or mark a few more words
        as Learning in the reader.
      </div>
      <div
        v-else-if="review.stats.learning === 0"
        class="mt-6 rounded-lg border border-border-subtle bg-bg-elevated px-5 py-4 text-center text-sm text-fg-muted"
      >
        No words in Learning yet. Click any word in the reader, then choose
        "Learning" from the popover.
      </div>
    </div>

    <!-- Loading state -->
    <div
      v-else-if="review.loading"
      class="flex items-center justify-center py-16"
    >
      <span
        class="inline-block size-6 animate-spin rounded-full border-2 border-fg-muted border-t-transparent"
      />
    </div>

    <!-- Session header + card -->
    <div v-else-if="card" class="space-y-6">
      <div class="flex items-center justify-between">
        <p
          class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          {{ review.mode }} · card {{ idx }} / {{ total }}
        </p>
        <button
          type="button"
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle transition-colors hover:text-fg"
          @click="review.reset()"
        >
          End session
        </button>
      </div>

      <!-- Progress bar -->
      <div class="h-[3px] w-full overflow-hidden rounded-full bg-bg-sunken">
        <div
          class="h-full rounded-full bg-accent transition-[width] duration-200"
          :style="{
            width: total > 0 ? `${(review.cursor / total) * 100}%` : '0%',
          }"
        />
      </div>

      <!-- Card -->
      <div
        class="rounded-2xl border border-border-subtle bg-bg-elevated px-6 py-10 text-center sm:px-10 sm:py-14"
      >
        <!-- Recognition mode -->
        <template v-if="review.mode === 'recognition'">
          <p
            v-if="card.hsk_level"
            class="mb-4 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            {{ card.hsk_level }}
          </p>
          <p class="font-cn-serif text-6xl leading-none text-fg sm:text-7xl">
            {{ card.word }}
          </p>
          <div v-if="revealed" class="mt-6 space-y-1.5">
            <p class="font-sans text-base text-fg-muted">{{ card.pinyin }}</p>
            <p class="font-display text-xl text-fg">{{ card.meaning }}</p>
            <ul
              v-if="card.meanings && card.meanings.length > 1"
              class="mt-1 space-y-0.5 text-sm text-fg-muted"
            >
              <li v-for="(m, i) in card.meanings.slice(1)" :key="i">{{ m }}</li>
            </ul>
          </div>

          <button
            v-if="!revealed"
            type="button"
            class="mt-8 inline-flex items-center gap-2 rounded-full border border-border bg-bg-elevated px-5 py-2 text-sm font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
            @click="reveal"
          >
            Show answer
            <span class="font-mono text-[9px] uppercase tracking-wider opacity-70">
              (space)
            </span>
          </button>
        </template>

        <!-- Dictation mode -->
        <template v-else-if="review.mode === 'dictation'">
          <button
            type="button"
            class="mx-auto inline-flex size-20 items-center justify-center rounded-full border border-border bg-bg-elevated text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:opacity-50"
            :disabled="ttsLoading"
            aria-label="Play word"
            @click="playTts"
          >
            <span
              v-if="ttsLoading"
              class="inline-block size-6 animate-spin rounded-full border-2 border-current border-t-transparent"
            />
            <svg v-else width="28" height="28" viewBox="0 0 28 28" fill="none">
              <path d="M5 10h4l5-4v16l-5-4H5v-8z" fill="currentColor" />
              <path
                d="M18 9c2 2 2 8 0 10M21 6c4 3 4 13 0 16"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
              />
            </svg>
          </button>

          <div class="mt-8">
            <input
              v-model="dictationInput"
              :readonly="dictationFeedback !== ''"
              type="text"
              placeholder="Type the hanzi or pinyin"
              autocomplete="off"
              autocapitalize="off"
              autocorrect="off"
              spellcheck="false"
              class="w-full max-w-md rounded-lg border border-border bg-bg-elevated px-4 py-3 text-center font-cn-serif text-2xl text-fg focus:border-accent focus:outline-none"
              @keydown.enter.prevent="
                dictationFeedback === ''
                  ? submitDictation()
                  : dictationContinue()
              "
            />
          </div>

          <div v-if="dictationFeedback === ''" class="mt-6">
            <button
              type="button"
              class="rounded-full bg-accent px-5 py-2 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
              :disabled="!dictationInput.trim()"
              @click="submitDictation"
            >
              Check
            </button>
          </div>

          <div v-else class="mt-6 space-y-2">
            <p
              class="font-mono text-[11px] uppercase tracking-wider"
              :class="
                dictationFeedback === 'correct' ? 'text-emerald-600 dark:text-emerald-300' : 'text-red-700 dark:text-red-300'
              "
            >
              {{ dictationFeedback === "correct" ? "Correct" : "Not quite" }}
            </p>
            <p class="font-cn-serif text-3xl text-fg">{{ card.word }}</p>
            <p class="font-sans text-sm text-fg-muted">{{ card.pinyin }}</p>
            <p class="font-display text-base text-fg">{{ card.meaning }}</p>
          </div>
        </template>
      </div>

      <!-- Grade row — visible after reveal in recognition, after answer in dictation. -->
      <div
        v-if="
          (review.mode === 'recognition' && revealed) ||
          (review.mode === 'dictation' && dictationFeedback !== '')
        "
        class="grid grid-cols-4 gap-2"
      >
        <button
          type="button"
          :disabled="review.grading"
          class="rounded-lg border border-border bg-bg-elevated px-3 py-3 transition-colors hover:border-red-500 hover:bg-red-50 disabled:opacity-50 dark:hover:bg-red-500/10"
          @click="gradeAndAdvance(1)"
        >
          <p class="font-display text-base font-medium text-red-700 dark:text-red-300">
            Again
          </p>
          <p
            class="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
          >
            &lt; 10m
          </p>
        </button>
        <button
          type="button"
          :disabled="review.grading"
          class="rounded-lg border border-border bg-bg-elevated px-3 py-3 transition-colors hover:border-amber-500 hover:bg-amber-50 disabled:opacity-50 dark:hover:bg-amber-500/10"
          @click="gradeAndAdvance(2)"
        >
          <p class="font-display text-base font-medium text-amber-700 dark:text-amber-300">
            Hard
          </p>
          <p
            class="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
          >
            soon
          </p>
        </button>
        <button
          type="button"
          :disabled="review.grading"
          class="rounded-lg border border-border bg-bg-elevated px-3 py-3 transition-colors hover:border-emerald-500 hover:bg-emerald-50 disabled:opacity-50 dark:hover:bg-emerald-500/10"
          @click="gradeAndAdvance(3)"
        >
          <p class="font-display text-base font-medium text-emerald-700 dark:text-emerald-300">
            Good
          </p>
          <p
            class="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
          >
            schedule
          </p>
        </button>
        <button
          type="button"
          :disabled="review.grading"
          class="rounded-lg border border-border bg-bg-elevated px-3 py-3 transition-colors hover:border-sky-500 hover:bg-sky-50 disabled:opacity-50 dark:hover:bg-sky-500/10"
          @click="gradeAndAdvance(4)"
        >
          <p class="font-display text-base font-medium text-sky-700 dark:text-sky-300">
            Easy
          </p>
          <p
            class="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
          >
            push back
          </p>
        </button>
      </div>
    </div>

    <!-- Session complete -->
    <div
      v-else-if="auth.isAuthed && review.sessionGraded > 0 && review.queue.length > 0"
      class="rounded-lg border border-border-subtle bg-bg-elevated px-6 py-10 text-center"
    >
      <p class="font-display text-xl font-medium text-fg">
        Session complete.
      </p>
      <p class="mt-2 text-sm text-fg-muted">
        {{ review.sessionGraded.toLocaleString() }} card{{
          review.sessionGraded === 1 ? "" : "s"
        }}
        reviewed. New due cards may have surfaced since you started.
      </p>
      <div class="mt-6 flex justify-center gap-3">
        <button
          type="button"
          class="rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
          @click="start(review.mode)"
        >
          Continue
        </button>
        <button
          type="button"
          class="rounded-full border border-border px-4 py-1.5 text-sm text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
          @click="review.reset()"
        >
          Done
        </button>
      </div>
    </div>
  </section>
</template>

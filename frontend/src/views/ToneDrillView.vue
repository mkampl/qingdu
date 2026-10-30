<script setup lang="ts">
/**
 * Tone practice: hear a word, pick its tones from choices that differ only
 * in tone. Real minimal pairs (买 mǎi / 卖 mài) carry their hanzi and can
 * be played to compare. Practice only: nothing goes into the review
 * schedule. Keys: 1–4 pick, space replays, enter goes on.
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import * as api from "@/api/client";
import type { ToneDrillItem } from "@/api/client";
import Button from "@/components/ui/Button.vue";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";

const auth = useAuthStore();
const authModals = useAuthModalsStore();

const items = ref<ToneDrillItem[]>([]);
const index = ref(0);
const picked = ref<number | null>(null);
const results = ref<boolean[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const playing = ref(false);

const item = computed(() => items.value[index.value] ?? null);
const done = computed(() => items.value.length > 0 && index.value >= items.value.length);
const score = computed(() => results.value.filter(Boolean).length);
const misses = computed(() => items.value.filter((_, i) => results.value[i] === false));

let audio: HTMLAudioElement | null = null;
let audioUrl: string | null = null;
let seq = 0;

function stopAudio() {
  audio?.pause();
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audio = null;
  audioUrl = null;
}

async function play(text: string) {
  stopAudio();
  const mine = ++seq;
  playing.value = true;
  try {
    const r = await api.tts(text);
    if (!r.ok) throw new Error("TTS failed");
    const blob = await r.blob();
    if (mine !== seq) return;
    audioUrl = URL.createObjectURL(blob);
    audio = new Audio(audioUrl);
    await audio.play();
  } catch {
    /* the play button stays available */
  } finally {
    if (mine === seq) playing.value = false;
  }
}

async function load() {
  if (!auth.isAuthed) return;
  loading.value = true;
  error.value = null;
  try {
    items.value = (await api.getToneDrill(12)).items;
    index.value = 0;
    picked.value = null;
    results.value = [];
    if (item.value) void play(item.value.word);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Couldn't load the practice.";
  } finally {
    loading.value = false;
  }
}

function pick(i: number) {
  if (!item.value || picked.value !== null) return;
  picked.value = i;
  results.value[index.value] = i === item.value.answer;
}

function next() {
  if (picked.value === null) return;
  picked.value = null;
  index.value += 1;
  if (item.value) void play(item.value.word);
}

function choiceClass(i: number): string {
  if (picked.value === null) {
    return "border-border hover:border-accent hover:bg-bg-sunken";
  }
  if (i === item.value?.answer) {
    return "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  }
  if (i === picked.value) return "border-red-400 bg-red-500/10 text-red-700 dark:text-red-300";
  return "border-border-subtle opacity-60";
}

function onKey(e: KeyboardEvent) {
  const target = e.target as HTMLElement | null;
  if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
  if (!item.value) return;
  if (/^[1-4]$/.test(e.key) && picked.value === null) {
    const i = Number(e.key) - 1;
    if (i < item.value.choices.length) pick(i);
  } else if (e.key === " ") {
    e.preventDefault();
    void play(item.value.word);
  } else if (e.key === "Enter" && picked.value !== null) {
    next();
  }
}

onMounted(() => {
  window.addEventListener("keydown", onKey);
  void load();
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  seq++;
  stopAudio();
});
</script>

<template>
  <section class="mx-auto max-w-xl px-5 py-10 sm:px-8 md:py-14">
    <header class="mb-8">
      <RouterLink
        to="/review"
        class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
      >
        ← Review
      </RouterLink>
      <h1 class="mt-2 font-display text-2xl font-medium tracking-tight text-fg">
        Tone practice
      </h1>
      <p class="mt-1 text-sm text-fg-muted">
        Listen and pick the tones. Practice only; your review schedule stays as it is.
      </p>
    </header>

    <div v-if="!auth.isAuthed" class="rounded-lg border border-border-subtle bg-bg-elevated p-8 text-center">
      <p class="font-display italic text-fg-muted">Sign in to practice with your own words.</p>
      <Button variant="primary" size="sm" class="mt-4" @click="authModals.openLogin()">Sign in</Button>
    </div>

    <p v-else-if="loading" class="font-display italic text-fg-muted">Picking words…</p>
    <p v-else-if="error" class="text-sm text-red-700 dark:text-red-300" role="alert">{{ error }}</p>
    <p v-else-if="!items.length" class="font-display italic text-fg-muted">
      No words to practice yet.
    </p>

    <!-- Result -->
    <div v-else-if="done" class="space-y-5">
      <p class="font-display text-3xl text-fg">
        {{ score }} <span class="text-fg-muted">/ {{ items.length }}</span>
      </p>
      <div v-if="misses.length">
        <p class="mb-2 font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
          Listen again
        </p>
        <ul class="divide-y divide-border-subtle rounded-md border border-border-subtle">
          <li v-for="m in misses" :key="m.word" class="flex items-center gap-3 px-3 py-2">
            <button
              type="button"
              class="rounded-full border border-border p-1.5 text-fg-muted hover:border-accent hover:text-accent"
              :aria-label="`Play ${m.word}`"
              @click="play(m.word)"
            >
              ▶
            </button>
            <span class="text-cn-serif text-xl text-fg">{{ m.word }}</span>
            <span class="text-sm text-fg">{{ m.pinyin }}</span>
            <span class="truncate text-xs text-fg-muted">{{ m.meaning }}</span>
          </li>
        </ul>
      </div>
      <Button variant="primary" size="sm" @click="load">Another round</Button>
    </div>

    <!-- Current word -->
    <div v-else-if="item" class="space-y-6">
      <p class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
        {{ index + 1 }} / {{ items.length }}
      </p>
      <div class="flex items-center gap-4">
        <button
          type="button"
          class="flex size-16 items-center justify-center rounded-full border-2 border-accent text-2xl text-accent transition-colors hover:bg-accent/10"
          :class="{ 'animate-pulse': playing }"
          aria-label="Play the word (space)"
          title="Play again (space)"
          @click="play(item.word)"
        >
          ▶
        </button>
        <div v-if="picked !== null">
          <p class="text-cn-serif text-4xl text-fg">{{ item.word }}</p>
          <p class="text-sm text-fg-muted">{{ item.pinyin }} · {{ item.meaning }}</p>
        </div>
        <p v-else class="text-sm text-fg-muted">Which tones do you hear?</p>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <button
          v-for="(c, i) in item.choices"
          :key="c.pinyin"
          type="button"
          class="flex flex-col items-start rounded-lg border px-4 py-3 text-left transition-colors"
          :class="choiceClass(i)"
          :disabled="picked !== null && !c.word"
          @click="picked === null ? pick(i) : c.word ? play(c.word) : undefined"
        >
          <span class="font-mono text-[10px] text-fg-subtle">{{ i + 1 }}</span>
          <span class="text-xl">{{ c.pinyin }}</span>
          <span v-if="picked !== null && c.word" class="text-cn-serif text-sm text-fg-muted">
            {{ c.word }} · tap to hear
          </span>
        </button>
      </div>

      <div v-if="picked !== null" class="flex items-center justify-between">
        <p class="text-sm" :class="results[index] ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-700 dark:text-red-300'">
          {{ results[index] ? "Right." : `It's ${item.pinyin}.` }}
        </p>
        <Button variant="primary" size="sm" @click="next">
          {{ index + 1 < items.length ? "Next" : "See result" }}
        </Button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
/**
 * Welcome for a new account: find the reading level with a short word
 * test (utils/placement), mark the words below it as known, set how many
 * new words a day, and point to texts that fit. Shown once (the
 * `onboarded` setting, kept on the account); Settings can open it again.
 */
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import * as api from "@/api/client";
import type { PlacementItem } from "@/api/client";
import Button from "@/components/ui/Button.vue";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";
import { ROUND_SIZE, afterRound, levelLabel, start, type PlacementState } from "@/utils/placement";

type Stage = "intro" | "test" | "result" | "done";

const auth = useAuthStore();
const settings = useSettingsStore();
const toasts = useToastStore();
const userWords = useUserWordsStore();

const stage = ref<Stage>("intro");
const state = ref<PlacementState>(start(1));
const items = ref<PlacementItem[]>([]);
const index = ref(0);
const roundCorrect = ref(0);
const picked = ref<number | null>(null);
const asked = ref<string[]>([]);
const loading = ref(false);
const level = ref(0);
const markKnown = ref(true);
const daily = ref(5);
const saving = ref(false);
const inserted = ref(0);

const item = computed(() => items.value[index.value] ?? null);

const STARTS = [
  { level: 0, label: "I'm new to Chinese", hint: "Start from the first words" },
  { level: 1, label: "I know some words", hint: "The test starts at HSK 1" },
  { level: 3, label: "I can read simple texts", hint: "The test starts at HSK 3" },
  { level: 5, label: "I read quite well", hint: "The test starts at HSK 5" },
];

async function loadRound(lvl: number) {
  loading.value = true;
  try {
    const r = await api.getPlacementItems(lvl, ROUND_SIZE, asked.value);
    items.value = r.items;
    asked.value = [...asked.value, ...r.items.map((i) => i.word)];
    index.value = 0;
    roundCorrect.value = 0;
    picked.value = null;
  } catch (e) {
    toasts.error(e instanceof Error ? e.message : "Couldn't load the test.");
    stage.value = "intro";
  } finally {
    loading.value = false;
  }
}

function begin(startLevel: number) {
  if (startLevel === 0) {
    level.value = 0;
    stage.value = "result";
    return;
  }
  state.value = start(startLevel);
  asked.value = [];
  stage.value = "test";
  void loadRound(startLevel);
}

function answer(i: number | null) {
  if (!item.value || picked.value !== null) return;
  picked.value = i ?? -1;
  if (i === item.value.answer) roundCorrect.value += 1;
  setTimeout(() => void next(), 700);
}

async function next() {
  if (index.value + 1 < items.value.length) {
    index.value += 1;
    picked.value = null;
    return;
  }
  const r = afterRound(state.value, roundCorrect.value);
  state.value = r.state;
  if (r.step.done) {
    level.value = r.step.level;
    stage.value = "result";
  } else {
    await loadRound(r.step.level);
  }
}

async function finish() {
  saving.value = true;
  try {
    if (markKnown.value && level.value > 0) {
      inserted.value = (await api.finishPlacement(level.value)).inserted;
    }
    await auth.updateSettings({ daily_new_words: daily.value, hsk_focus_version: "new" });
    settings.hskVersion = "new";
    settings.onboarded = true;
    void userWords.hydrate();
    stage.value = "done";
  } catch (e) {
    toasts.error(e instanceof Error ? e.message : "Couldn't save.");
  } finally {
    saving.value = false;
  }
}

function skip() {
  settings.onboarded = true;
}

// Library level to start reading at: just above what is known.
const readLevel = computed(() => Math.min(9, Math.max(1, level.value === 7 ? 7 : level.value + 1)));
const progressText = computed(
  () => `${levelLabel(state.value.level)} · ${index.value + 1} / ${items.value.length || ROUND_SIZE}`,
);
</script>

<template>
  <section class="mx-auto max-w-xl px-5 py-10 sm:px-8 md:py-14">
    <!-- Intro -->
    <template v-if="stage === 'intro'">
      <h1 class="font-display text-3xl font-medium tracking-tight text-fg">Welcome to Qingdu</h1>
      <p class="mt-3 text-sm leading-relaxed text-fg-muted">
        Let's find your level, so Qingdu marks the words you already know and
        suggests texts you can read. A short test: pick the meaning of a few
        words per level; about three minutes.
      </p>
      <ul class="mt-6 space-y-2">
        <li v-for="s in STARTS" :key="s.level">
          <button
            type="button"
            class="w-full rounded-lg border border-border bg-bg-elevated px-4 py-3 text-left transition-colors hover:border-accent"
            @click="begin(s.level)"
          >
            <span class="block font-display text-base text-fg">{{ s.label }}</span>
            <span class="block text-xs text-fg-muted">{{ s.hint }}</span>
          </button>
        </li>
      </ul>
      <RouterLink
        to="/"
        class="mt-6 inline-block font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
        @click="skip"
      >
        Skip for now
      </RouterLink>
    </template>

    <!-- Test -->
    <template v-else-if="stage === 'test'">
      <p class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">{{ progressText }}</p>
      <p v-if="loading || !item" class="mt-6 font-display italic text-fg-muted">Picking words…</p>
      <div v-else class="mt-4 space-y-5">
        <p class="text-cn-serif text-center text-6xl text-fg">{{ item.word }}</p>
        <p class="h-5 text-center text-sm text-fg-muted">
          <template v-if="picked !== null">{{ item.pinyin }}</template>
        </p>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <button
            v-for="(c, i) in item.choices"
            :key="c"
            type="button"
            class="rounded-lg border px-4 py-3 text-left text-sm transition-colors"
            :class="
              picked === null
                ? 'border-border hover:border-accent'
                : i === item.answer
                  ? 'border-emerald-500 bg-emerald-500/10'
                  : i === picked
                    ? 'border-red-400 bg-red-500/10'
                    : 'border-border-subtle opacity-50'
            "
            @click="answer(i)"
          >
            {{ c }}
          </button>
        </div>
        <button
          type="button"
          class="w-full rounded-lg border border-dashed border-border px-4 py-2 text-sm text-fg-muted hover:text-fg"
          :disabled="picked !== null"
          @click="answer(null)"
        >
          I don't know
        </button>
      </div>
    </template>

    <!-- Result -->
    <template v-else-if="stage === 'result'">
      <h1 class="font-display text-2xl font-medium text-fg">
        <template v-if="level > 0">You know most words up to {{ levelLabel(level) }}</template>
        <template v-else>Let's start from the beginning</template>
      </h1>
      <label v-if="level > 0" class="mt-5 flex items-start gap-3 text-sm text-fg">
        <input v-model="markKnown" type="checkbox" class="mt-1 accent-accent" />
        <span>
          Mark the words of HSK 1–{{ level === 7 ? "9" : level }} as known
          <span class="block text-xs text-fg-muted">
            Texts then show only the words you don't know yet; review schedules
            them far out. You can change any word later.
          </span>
        </span>
      </label>
      <fieldset class="mt-5">
        <legend class="mb-2 text-sm text-fg">New words to learn each day</legend>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="n in [0, 5, 10, 15]"
            :key="n"
            type="button"
            class="rounded-full border px-3 py-1 text-sm transition-colors"
            :class="daily === n ? 'border-accent bg-accent/10 text-accent' : 'border-border text-fg-muted'"
            @click="daily = n"
          >
            {{ n === 0 ? "None, I pick them" : n }}
          </button>
        </div>
      </fieldset>
      <Button variant="primary" size="sm" class="mt-6" :loading="saving" @click="finish">
        Start reading
      </Button>
    </template>

    <!-- Done -->
    <template v-else>
      <h1 class="font-display text-2xl font-medium text-fg">All set</h1>
      <p class="mt-2 text-sm text-fg-muted">
        <template v-if="inserted">{{ inserted.toLocaleString() }} words marked as known. </template>
        These are good next steps:
      </p>
      <ul class="mt-5 space-y-2">
        <li>
          <RouterLink
            :to="{ path: '/library', query: { level: String(readLevel) } }"
            class="block rounded-lg border border-border bg-bg-elevated px-4 py-3 hover:border-accent"
          >
            <span class="block font-display text-base text-fg">Read a library text at HSK {{ readLevel }}</span>
            <span class="block text-xs text-fg-muted">Short texts with a quiz, sorted by how readable they are for you</span>
          </RouterLink>
        </li>
        <li>
          <RouterLink to="/discover" class="block rounded-lg border border-border bg-bg-elevated px-4 py-3 hover:border-accent">
            <span class="block font-display text-base text-fg">Texts picked for you</span>
            <span class="block text-xs text-fg-muted">Where you already know most of the words</span>
          </RouterLink>
        </li>
        <li>
          <RouterLink to="/" class="block rounded-lg border border-border bg-bg-elevated px-4 py-3 hover:border-accent">
            <span class="block font-display text-base text-fg">Paste your own text</span>
            <span class="block text-xs text-fg-muted">Anything Chinese: an article, a chat, a song</span>
          </RouterLink>
        </li>
      </ul>
    </template>
  </section>
</template>

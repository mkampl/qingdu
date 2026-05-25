<script setup lang="ts">
/**
 * Pronunciation check via the Web Speech API.
 *
 * Tap the mic, speak the target word, browser transcribes, we compare.
 * Browser support: Chrome / Edge / Safari (desktop + iOS). Firefox has
 * no SpeechRecognition implementation as of 2026, so the button is
 * hidden entirely there — falling back gracefully rather than nagging.
 *
 * Language: we request zh-CN for simp/auto users, zh-TW for trad users
 * so the recognised text comes back in the same script we asked the
 * user to read, and a string compare actually works.
 */
import { computed, onBeforeUnmount, ref, watch } from "vue";

import { useAuthStore } from "@/stores/auth";

const props = defineProps<{
  /** The hanzi to compare against (already in the user's display script). */
  target: string;
}>();

const auth = useAuthStore();

// Browser detection: vendor-prefixed in Safari/older Chromium.
type RecognitionWindow = Window & {
  SpeechRecognition?: SpeechRecognitionCtor;
  webkitSpeechRecognition?: SpeechRecognitionCtor;
};
interface SpeechRecognitionCtor {
  new (): SpeechRecognitionInstance;
}
interface SpeechRecognitionInstance {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEvt) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
interface SpeechRecognitionEvt {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}
const win = window as RecognitionWindow;
const Ctor = win.SpeechRecognition || win.webkitSpeechRecognition;
const supported = !!Ctor;

type Status =
  | "idle"
  | "listening"
  | "matched"
  | "close"
  | "wrong"
  | "no-speech";
const status = ref<Status>("idle");
const transcript = ref("");

let rec: SpeechRecognitionInstance | null = null;

const lang = computed(() =>
  auth.user?.display_script === "trad" ? "zh-TW" : "zh-CN",
);

function normalize(s: string): string {
  // Strip punctuation + whitespace that Web Speech tends to attach to the end.
  return s.replace(/[。,，.！!？?；;、\s]/g, "");
}

function start() {
  if (!supported || !Ctor || status.value === "listening" || !props.target)
    return;
  transcript.value = "";
  status.value = "listening";
  const r = new Ctor();
  r.lang = lang.value;
  r.continuous = false;
  r.interimResults = false;
  r.maxAlternatives = 3;
  r.onresult = (event) => {
    const alts: string[] = [];
    const list = event.results[0];
    for (let i = 0; i < list.length; i++) alts.push(list[i].transcript);
    transcript.value = alts[0] ?? "";
    const target = normalize(props.target);
    const normalised = alts.map(normalize);
    if (normalised.some((a) => a === target)) {
      status.value = "matched";
    } else if (
      normalised.some(
        (a) => (a && target.includes(a)) || (a && a.includes(target)),
      )
    ) {
      status.value = "close";
    } else {
      status.value = "wrong";
    }
  };
  r.onerror = (event) => {
    status.value = event.error === "no-speech" ? "no-speech" : "wrong";
  };
  r.onend = () => {
    if (status.value === "listening") status.value = "idle";
  };
  rec = r;
  r.start();
}

function stop() {
  rec?.stop();
}

function reset() {
  rec?.abort();
  rec = null;
  status.value = "idle";
  transcript.value = "";
}

// New target → forget the previous attempt so the popover doesn't show
// stale feedback from a different word.
watch(() => props.target, reset);

onBeforeUnmount(() => {
  rec?.abort();
});

const statusLabel = computed(() => {
  switch (status.value) {
    case "matched":
      return "✓ Match";
    case "close":
      return "Close";
    case "wrong":
      return "Try again";
    case "no-speech":
      return "Didn't hear you";
    case "listening":
      return "Listening…";
    default:
      return "";
  }
});

const statusColor = computed(() => {
  switch (status.value) {
    case "matched":
      return "text-emerald-600 dark:text-emerald-300";
    case "close":
      return "text-amber-600 dark:text-amber-300";
    case "wrong":
    case "no-speech":
      return "text-red-700 dark:text-red-300";
    default:
      return "text-fg-subtle";
  }
});
</script>

<template>
  <div v-if="supported" class="flex flex-col items-end gap-1">
    <button
      type="button"
      class="inline-flex items-center justify-center rounded-md border border-border bg-bg-elevated p-2 text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
      :class="{
        'border-red-500 text-red-700 dark:text-red-300': status === 'listening',
      }"
      :aria-label="status === 'listening' ? 'Stop' : 'Check pronunciation'"
      @click="status === 'listening' ? stop() : start()"
    >
      <svg
        v-if="status !== 'listening'"
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
      >
        <rect x="6" y="2" width="4" height="7" rx="2" fill="currentColor" />
        <path
          d="M3.5 7c0 2.5 2 4.5 4.5 4.5s4.5-2 4.5-4.5M8 11.5V14"
          stroke="currentColor"
          stroke-width="1.2"
          stroke-linecap="round"
        />
      </svg>
      <span
        v-else
        class="inline-block size-3 animate-pulse rounded-full bg-current"
      />
    </button>
    <p
      v-if="statusLabel"
      class="font-mono text-[10px] uppercase tracking-wider"
      :class="statusColor"
    >
      {{ statusLabel }}
    </p>
    <p
      v-if="transcript && status !== 'listening'"
      class="font-cn-serif text-[11px] text-fg-muted"
    >
      heard: {{ transcript }}
    </p>
  </div>
</template>

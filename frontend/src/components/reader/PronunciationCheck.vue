<script setup lang="ts">
/**
 * Pronunciation check — MediaRecorder + server STT + tone-contour scoring.
 *
 * Cross-browser: any modern browser supports MediaRecorder (Firefox /
 * Chrome / Safari / Edge), so this works everywhere unlike the prior
 * Web-Speech-only version. Audio is uploaded to /api/pronounce which
 * runs faster-whisper + librosa.pyin and returns per-syllable scores.
 *
 * UI flow:
 *   idle → tap mic → "recording" → tap mic again → "scoring…" → result
 *
 * No auto-stop — the user controls when to finish. Tones live in pitch
 * shape, so trimming the audio too aggressively (VAD, fixed timeout)
 * loses signal we need for the contour comparison.
 */
import { onBeforeUnmount, ref, watch } from "vue";

import { apiUrl } from "@/api/client";

const props = defineProps<{
  /** Hanzi to compare against (in the user's display script). */
  target: string;
  /** Tone-marked pinyin per character, e.g. ["nǐ", "hǎo"]. */
  pinyin?: string[];
}>();

type Status = "idle" | "recording" | "scoring" | "done" | "error" | "denied";

const status = ref<Status>("idle");
const errorMessage = ref("");

interface SyllableScore {
  char: string;
  pinyin: string;
  expected_tone: number;
  transcribed_char: string;
  char_match: boolean;
  tone_score: number;
}
interface PronounceResponse {
  transcript: string;
  overall_score: number;
  syllables: SyllableScore[];
  notes: string[];
}
const result = ref<PronounceResponse | null>(null);

let recorder: MediaRecorder | null = null;
let chunks: BlobPart[] = [];
let stream: MediaStream | null = null;

// Browser support — MediaRecorder is universal in modern browsers, but
// the available mime types vary. We pick the most-supported one and let
// the server's ffmpeg-backed decoder figure out the rest.
function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
  ];
  for (const c of candidates) {
    if (MediaRecorder.isTypeSupported(c)) return c;
  }
  return "";
}
const supported =
  typeof navigator !== "undefined" &&
  !!navigator.mediaDevices &&
  !!pickMimeType();

async function start() {
  if (!supported || status.value === "recording") return;
  errorMessage.value = "";
  result.value = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    const name = (err as DOMException)?.name;
    if (name === "NotAllowedError" || name === "SecurityError") {
      status.value = "denied";
      errorMessage.value = "Microphone permission denied.";
    } else {
      status.value = "error";
      errorMessage.value = "Couldn't open the microphone.";
    }
    return;
  }
  const mime = pickMimeType();
  recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  chunks = [];
  recorder.ondataavailable = (e) => {
    if (e.data && e.data.size) chunks.push(e.data);
  };
  recorder.onstop = () => void onRecordingDone(mime);
  recorder.start();
  status.value = "recording";
}

function stop() {
  if (recorder && recorder.state !== "inactive") recorder.stop();
}

async function onRecordingDone(mime: string) {
  // Tear down the stream so the mic indicator drops immediately.
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;

  if (!chunks.length) {
    status.value = "idle";
    return;
  }
  status.value = "scoring";
  const blob = new Blob(chunks, { type: mime || "audio/webm" });
  const form = new FormData();
  form.append("audio", blob, "pronounce.webm");
  form.append("word", props.target);
  if (props.pinyin && props.pinyin.length) {
    form.append("pinyin", props.pinyin.join(","));
  }
  try {
    const token = localStorage.getItem("qingdu.token.v2");
    const r = await fetch(apiUrl("/api/pronounce"), {
      method: "POST",
      body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!r.ok) {
      const detail = (await r.json().catch(() => ({})))?.detail ?? r.statusText;
      throw new Error(typeof detail === "string" ? detail : `HTTP ${r.status}`);
    }
    result.value = (await r.json()) as PronounceResponse;
    status.value = "done";
  } catch (err) {
    status.value = "error";
    errorMessage.value =
      err instanceof Error ? err.message : "Couldn't score audio.";
  }
}

function reset() {
  if (recorder && recorder.state !== "inactive") {
    try {
      recorder.stop();
    } catch {
      /* ignore */
    }
  }
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
  recorder = null;
  chunks = [];
  status.value = "idle";
  result.value = null;
  errorMessage.value = "";
}

// New target → drop the previous attempt.
watch(() => props.target, reset);

onBeforeUnmount(reset);

// Map a 0..1 tone score to a tachometer-style label + color class.
function toneLabel(s: number): { text: string; cls: string } {
  if (s >= 0.8)
    return { text: "great", cls: "text-emerald-600 dark:text-emerald-300" };
  if (s >= 0.55)
    return { text: "ok", cls: "text-amber-600 dark:text-amber-300" };
  if (s >= 0.3)
    return { text: "off", cls: "text-orange-600 dark:text-orange-300" };
  return { text: "way off", cls: "text-red-700 dark:text-red-300" };
}
</script>

<template>
  <div v-if="supported" class="flex flex-col items-end gap-2">
    <div class="flex items-center gap-2">
      <button
        type="button"
        class="inline-flex items-center justify-center rounded-md border border-border bg-bg-elevated p-2 text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:opacity-50"
        :class="{
          'border-red-500 text-red-700 dark:text-red-300':
            status === 'recording',
        }"
        :disabled="status === 'scoring'"
        :aria-label="
          status === 'recording' ? 'Stop recording' : 'Check pronunciation'
        "
        @click="status === 'recording' ? stop() : start()"
      >
        <span
          v-if="status === 'scoring'"
          class="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
        <span
          v-else-if="status === 'recording'"
          class="inline-block size-3 animate-pulse rounded-full bg-current"
        />
        <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="none">
          <rect x="6" y="2" width="4" height="7" rx="2" fill="currentColor" />
          <path
            d="M3.5 7c0 2.5 2 4.5 4.5 4.5s4.5-2 4.5-4.5M8 11.5V14"
            stroke="currentColor"
            stroke-width="1.2"
            stroke-linecap="round"
          />
        </svg>
      </button>
    </div>

    <p
      v-if="status === 'recording'"
      class="font-mono text-[10px] uppercase tracking-wider text-red-700 dark:text-red-300"
    >
      Recording — tap to stop
    </p>
    <p
      v-else-if="status === 'scoring'"
      class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
    >
      Scoring…
    </p>
    <p
      v-else-if="status === 'denied' || status === 'error'"
      class="max-w-[180px] text-right font-mono text-[10px] uppercase tracking-wider text-red-700 dark:text-red-300"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="status === 'done' && result"
      class="flex w-full max-w-[220px] flex-col items-end gap-1.5 rounded-md border border-border-subtle bg-bg-sunken px-2.5 py-2"
    >
      <div
        v-for="(syl, i) in result.syllables"
        :key="i"
        class="flex w-full items-center justify-between gap-2"
      >
        <div class="flex items-baseline gap-1.5">
          <span class="font-cn-serif text-base text-fg">{{ syl.char }}</span>
          <span class="font-mono text-[10px] text-fg-subtle">
            T{{ syl.expected_tone }}
          </span>
        </div>
        <div class="flex items-center gap-1.5">
          <span
            class="font-mono text-[10px]"
            :class="
              syl.char_match
                ? 'text-fg-muted'
                : 'text-red-700 dark:text-red-300'
            "
          >
            {{ syl.char_match ? "✓" : "✗" }}
          </span>
          <span
            class="font-mono text-[10px] uppercase tracking-wider"
            :class="toneLabel(syl.tone_score).cls"
          >
            {{ toneLabel(syl.tone_score).text }}
          </span>
        </div>
      </div>
      <p
        v-if="result.notes.length"
        class="mt-1 max-w-full text-right font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
      >
        {{ result.notes.join(" ") }}
      </p>
      <p
        v-if="result.transcript"
        class="font-cn-serif text-[11px] text-fg-muted"
      >
        heard: {{ result.transcript }}
      </p>
    </div>
  </div>
</template>

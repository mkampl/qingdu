import { computed, ref, watch } from "vue";
import { defineStore } from "pinia";

import { apiUrl } from "@/api/client";

/**
 * Continuous-narration player for the reader. Plays a queue of sentence
 * strings via `POST /api/tts/sentence`, advances on `audio.ended`, and
 * pre-fetches the next sentence while the current one plays so the gap
 * is near-zero on a warm cache.
 *
 * The reader subscribes to `currentSentenceKey` to highlight + auto-scroll.
 */
export interface PlayableSentence {
  /** Stable v-for key (matches Sentence.key from reader utils). */
  key: string;
  /** The Chinese text to read. */
  text: string;
}

const DEFAULT_RATE_KEY = "qingdu.player.rate";
const LISTEN_MODE_KEY = "qingdu.player.listenMode";

function readNumber(key: string, fallback: number): number {
  if (typeof localStorage === "undefined") return fallback;
  const raw = localStorage.getItem(key);
  if (!raw) return fallback;
  const n = parseFloat(raw);
  return Number.isFinite(n) ? n : fallback;
}

function readBool(key: string, fallback: boolean): boolean {
  if (typeof localStorage === "undefined") return fallback;
  const raw = localStorage.getItem(key);
  return raw === null ? fallback : raw === "1";
}

interface SentenceFetch {
  url: string;
  blob: Blob;
}

export const useAudioPlayerStore = defineStore("audioPlayer", () => {
  const queue = ref<PlayableSentence[]>([]);
  const cursor = ref(0);
  const playing = ref(false);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const playbackRate = ref(readNumber(DEFAULT_RATE_KEY, 1));
  const listenMode = ref(readBool(LISTEN_MODE_KEY, false));

  // Audio element lives in JS-land (not Vue ref) — we don't render it.
  let audio: HTMLAudioElement | null = null;
  // Pre-fetched MP3 blobs keyed by sentence key. Capped at a few entries so
  // a very long article doesn't pin the whole audio set in memory.
  const cache = new Map<string, SentenceFetch>();
  const CACHE_MAX = 6;

  const current = computed<PlayableSentence | null>(
    () => queue.value[cursor.value] ?? null,
  );
  const currentKey = computed(() => current.value?.key ?? null);
  const total = computed(() => queue.value.length);
  const hasQueue = computed(() => queue.value.length > 0);

  watch(playbackRate, (rate) => {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(DEFAULT_RATE_KEY, String(rate));
    }
    if (audio) audio.playbackRate = rate;
  });

  watch(listenMode, (on) => {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(LISTEN_MODE_KEY, on ? "1" : "0");
    }
  });

  function evictExcessCache(keepKeys: Set<string>) {
    for (const [key, entry] of cache) {
      if (!keepKeys.has(key)) {
        URL.revokeObjectURL(entry.url);
        cache.delete(key);
      }
    }
    // If we're still over the cap (shouldn't be — keepKeys is bounded by the
    // active window), drop oldest insertions.
    while (cache.size > CACHE_MAX) {
      const oldest = cache.keys().next().value;
      if (!oldest) break;
      const entry = cache.get(oldest);
      if (entry) URL.revokeObjectURL(entry.url);
      cache.delete(oldest);
    }
  }

  async function fetchSentence(
    sentence: PlayableSentence,
  ): Promise<SentenceFetch> {
    const hit = cache.get(sentence.key);
    if (hit) return hit;
    const r = await fetch(apiUrl("/api/tts/sentence"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: sentence.text }),
    });
    if (!r.ok) throw new Error(`TTS failed (${r.status})`);
    const blob = await r.blob();
    const entry: SentenceFetch = { blob, url: URL.createObjectURL(blob) };
    cache.set(sentence.key, entry);
    return entry;
  }

  function prefetchNext() {
    const next = queue.value[cursor.value + 1];
    if (!next || cache.has(next.key)) return;
    // Fire-and-forget; errors are not fatal — we'll surface them when the
    // player actually advances to that sentence.
    fetchSentence(next).catch(() => undefined);
  }

  function ensureAudioEl(): HTMLAudioElement {
    if (audio) return audio;
    audio = new Audio();
    audio.preload = "auto";
    audio.playbackRate = playbackRate.value;
    audio.addEventListener("ended", () => {
      // Auto-advance.
      void advance();
    });
    audio.addEventListener("error", () => {
      error.value = "Playback error";
      playing.value = false;
    });
    return audio;
  }

  async function playCurrent() {
    const c = current.value;
    if (!c) {
      playing.value = false;
      return;
    }
    loading.value = true;
    error.value = null;
    try {
      const fetched = await fetchSentence(c);
      // Evict everything but a small window around the cursor.
      const keep = new Set<string>();
      for (let i = -1; i <= 3; i++) {
        const k = queue.value[cursor.value + i]?.key;
        if (k) keep.add(k);
      }
      evictExcessCache(keep);

      const el = ensureAudioEl();
      el.src = fetched.url;
      el.playbackRate = playbackRate.value;
      await el.play();
      playing.value = true;
      // Kick off prefetch for the next one as soon as we start playing.
      prefetchNext();
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Couldn't play audio";
      playing.value = false;
    } finally {
      loading.value = false;
    }
  }

  async function advance() {
    if (cursor.value + 1 >= queue.value.length) {
      playing.value = false;
      return;
    }
    cursor.value += 1;
    await playCurrent();
  }

  async function rewind() {
    if (cursor.value <= 0) return;
    cursor.value -= 1;
    if (playing.value) await playCurrent();
  }

  async function play() {
    if (!queue.value.length) return;
    if (audio && audio.paused && audio.src) {
      await audio.play();
      playing.value = true;
      prefetchNext();
      return;
    }
    await playCurrent();
  }

  function pause() {
    if (audio && !audio.paused) audio.pause();
    playing.value = false;
  }

  async function toggle() {
    if (playing.value) pause();
    else await play();
  }

  async function jumpTo(key: string) {
    const idx = queue.value.findIndex((s) => s.key === key);
    if (idx === -1) return;
    cursor.value = idx;
    if (playing.value) await playCurrent();
  }

  function setQueue(next: PlayableSentence[]) {
    if (audio) {
      audio.pause();
      audio.src = "";
    }
    playing.value = false;
    cursor.value = 0;
    error.value = null;
    // Drop all cached blobs from the previous queue.
    for (const entry of cache.values()) URL.revokeObjectURL(entry.url);
    cache.clear();
    queue.value = next;
  }

  function setRate(rate: number) {
    playbackRate.value = Math.max(0.5, Math.min(2, rate));
  }

  function setListenMode(on: boolean) {
    listenMode.value = on;
  }

  function reset() {
    if (audio) {
      audio.pause();
      audio.src = "";
    }
    playing.value = false;
    cursor.value = 0;
    queue.value = [];
    error.value = null;
    for (const entry of cache.values()) URL.revokeObjectURL(entry.url);
    cache.clear();
  }

  return {
    queue,
    cursor,
    playing,
    loading,
    error,
    playbackRate,
    listenMode,
    current,
    currentKey,
    total,
    hasQueue,
    play,
    pause,
    toggle,
    advance,
    rewind,
    jumpTo,
    setQueue,
    setRate,
    setListenMode,
    reset,
  };
});

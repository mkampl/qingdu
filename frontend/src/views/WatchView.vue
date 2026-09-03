<script setup lang="ts">
/**
 * Watch & read — prototype (spike, not linked from nav yet).
 *
 * Paste a YouTube URL, embed the official player, fetch its Chinese
 * caption track through /api/media/youtube (already segmented + HSK/CEDICT
 * annotated by the backend), and keep the transcript in sync with
 * playback: highlight + auto-scroll the sentence being spoken, click a
 * word for the same popover the Reader uses, click a sentence to jump
 * the video there and fetch its translation.
 *
 * This proves the end-to-end mechanism (real captions -> real analysis ->
 * real sync) before deciding whether it's worth building into a proper
 * feature. See the Discover-page conversation for the licensing analysis
 * behind why this is built on open caption data instead of scraping a
 * paywalled transcript site.
 */
import { computed, nextTick, onBeforeUnmount, ref } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { YoutubeReadResponse, YoutubeSegment } from "@/api/client";
import type { WordInfo } from "@/api/types";
import WordPopover from "@/components/reader/WordPopover.vue";
import SentenceTranslation from "@/components/reader/SentenceTranslation.vue";
import { hskCssVar, levelForVersion } from "@/components/reader/utils";
import { useReaderStore } from "@/stores/reader";
import { useSettingsStore } from "@/stores/settings";
import { useToastStore } from "@/stores/toast";

// Minimal ambient shim for the bits of the YouTube IFrame Player API we
// use — not worth a whole @types/youtube dependency for a prototype.
interface YTPlayer {
  getCurrentTime(): number;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  destroy(): void;
}
declare global {
  interface Window {
    YT?: {
      Player: new (
        elementId: string,
        options: {
          videoId: string;
          events?: { onReady?: () => void };
        },
      ) => YTPlayer;
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

let ytApiPromise: Promise<void> | null = null;
function loadYoutubeApi(): Promise<void> {
  if (window.YT?.Player) return Promise.resolve();
  if (ytApiPromise) return ytApiPromise;
  ytApiPromise = new Promise((resolve) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      resolve();
    };
    const tag = document.createElement("script");
    tag.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(tag);
  });
  return ytApiPromise;
}

const reader = useReaderStore();
const settings = useSettingsStore();
const toast = useToastStore();

const urlInput = ref("");
const loading = ref(false);
const error = ref<string | null>(null);
const data = ref<YoutubeReadResponse | null>(null);

const currentTime = ref(0);
let player: YTPlayer | null = null;
let pollHandle: ReturnType<typeof setInterval> | null = null;

const activeIndex = computed(() => {
  if (!data.value) return -1;
  const segs = data.value.segments;
  const t = currentTime.value;
  const idx = segs.findIndex((s) => t >= s.start && t < s.end);
  if (idx !== -1) return idx;
  // Between the last segment's end and the video's actual end — keep the
  // last sentence highlighted rather than snapping to nothing.
  if (segs.length && t >= segs[segs.length - 1].start) return segs.length - 1;
  return -1;
});

let lastScrolledIndex = -1;
async function maybeAutoScroll() {
  const idx = activeIndex.value;
  if (idx === -1 || idx === lastScrolledIndex) return;
  lastScrolledIndex = idx;
  await nextTick();
  const el = document.querySelector(`[data-segment-index="${idx}"]`) as HTMLElement | null;
  el?.scrollIntoView({ block: "center", behavior: "smooth" });
}

function stopPolling() {
  if (pollHandle !== null) {
    clearInterval(pollHandle);
    pollHandle = null;
  }
}

function destroyPlayer() {
  stopPolling();
  player?.destroy();
  player = null;
}

async function loadVideo() {
  const url = urlInput.value.trim();
  if (!url) return;
  loading.value = true;
  error.value = null;
  destroyPlayer();
  data.value = null;
  currentTime.value = 0;
  lastScrolledIndex = -1;
  reader.reset();

  try {
    const result = await api.readYoutube(url);
    data.value = result;
    await loadYoutubeApi();
    await nextTick();
    player = new window.YT!.Player("watch-yt-player", {
      videoId: result.video_id,
      events: {
        onReady: () => {
          pollHandle = setInterval(() => {
            currentTime.value = player?.getCurrentTime() ?? 0;
            void maybeAutoScroll();
          }, 300);
        },
      },
    });
  } catch (e) {
    const message =
      e instanceof ApiError
        ? e.message
        : e instanceof Error
          ? e.message
          : "Couldn't load that video";
    error.value = message;
    toast.error(message);
  } finally {
    loading.value = false;
  }
}

function wordStyle(word: WordInfo): Record<string, string> | undefined {
  if (!word.is_hsk) return undefined;
  const color = hskCssVar(levelForVersion(word, settings.hskVersion));
  return { "--hsk-color": color };
}

function isClickableWord(word: WordInfo): boolean {
  return Boolean(word.is_hsk || word.meaning);
}

function onWordClick(word: WordInfo, event: MouseEvent, seg: YoutubeSegment, i: number) {
  if (!isClickableWord(word)) return;
  event.stopPropagation();
  const target = event.currentTarget as HTMLElement;
  reader.selectWord(word, target, { key: `seg-${i}`, text: seg.text });
}

function onSegmentClick(seg: YoutubeSegment, i: number) {
  player?.seekTo(seg.start, true);
  const key = `seg-${i}`;
  if (reader.openSentenceKey === key) {
    reader.closeSentence();
    return;
  }
  reader.toggleSentence(key);
  void reader.translateSentence(seg.text);
}

onBeforeUnmount(() => {
  destroyPlayer();
  reader.reset();
});
</script>

<template>
  <section class="mx-auto max-w-3xl px-4 py-6 sm:px-8 sm:py-10">
    <header class="mb-6">
      <div class="mb-1.5 flex items-baseline gap-3">
        <span
          class="font-mono text-[11px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
        >
          Prototype
        </span>
        <span class="h-px w-12 bg-border-subtle" aria-hidden="true" />
      </div>
      <h1 class="font-display text-xl font-medium tracking-tight text-fg sm:text-2xl">
        Watch &amp; read
      </h1>
      <p class="mt-1.5 max-w-prose text-sm leading-relaxed text-fg-muted">
        Paste a YouTube URL for a video with a Chinese caption track. The
        transcript below stays in sync with playback — click any word for
        pinyin and meaning, click a sentence to jump the video there and
        see its translation.
      </p>
    </header>

    <form class="mb-8 flex gap-2" @submit.prevent="loadVideo">
      <input
        v-model="urlInput"
        type="url"
        placeholder="https://www.youtube.com/watch?v=…"
        class="flex-1 rounded-lg border border-border bg-bg-elevated px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:border-accent focus:outline-none"
      />
      <button
        type="submit"
        :disabled="loading || !urlInput.trim()"
        class="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {{ loading ? "Loading…" : "Load" }}
      </button>
    </form>

    <p v-if="error" class="mb-6 rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-500">
      {{ error }}
    </p>

    <template v-if="data">
      <div class="mb-2 overflow-hidden rounded-lg bg-black">
        <div id="watch-yt-player" class="aspect-video w-full" />
      </div>
      <p
        v-if="data.is_generated"
        class="mb-6 text-xs italic leading-relaxed text-fg-subtle"
      >
        Auto-generated captions — sentence breaks are approximate, since
        YouTube's Chinese ASR rarely includes punctuation.
      </p>
      <p v-else class="mb-6 text-xs italic leading-relaxed text-fg-subtle">
        Manually-authored captions.
      </p>

      <div class="space-y-1">
        <div
          v-for="(seg, i) in data.segments"
          :key="i"
          :data-segment-index="i"
          class="cursor-pointer rounded-lg px-3 py-2 text-cn-serif text-lg leading-relaxed transition-colors"
          :class="i === activeIndex ? 'bg-accent/10' : 'hover:bg-bg-sunken'"
          @click="onSegmentClick(seg, i)"
        >
          <span
            v-for="(w, wi) in seg.words"
            :key="wi"
            class="hsk-wash"
            :class="{ 'cursor-pointer': isClickableWord(w) }"
            :style="wordStyle(w)"
            @click="onWordClick(w, $event, seg, i)"
          >{{ w.text }}</span>

          <SentenceTranslation
            v-if="reader.openSentenceKey === `seg-${i}`"
            :text="seg.text"
          />
        </div>
      </div>
    </template>

    <WordPopover />
  </section>
</template>

<style scoped>
.hsk-wash {
  color: var(--hsk-color, inherit);
}
</style>

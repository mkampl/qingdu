<script setup lang="ts">
import { computed, ref } from "vue";

import * as api from "@/api/client";
import { useReaderStore } from "@/stores/reader";

const props = defineProps<{ text: string }>();

const reader = useReaderStore();

const state = computed(() => reader.sentenceTranslations.get(props.text));

const sourceLabel = computed(() => {
  if (!state.value || state.value.status !== "ok") return null;
  const source = state.value.data.source;
  if (source === "deepl") return "DeepL";
  if (source === "google") return "Google";
  if (source === "mymemory") return "MyMemory";
  if (source === "cache") return "Cached";
  if (source === "package") return "Package translation";
  return source;
});

// Sentence playback uses the same /api/tts/{text} endpoint as the word
// popover. We keep a per-instance Audio element so a click during playback
// re-triggers from the start cleanly.
const ttsLoading = ref(false);
let currentAudio: HTMLAudioElement | null = null;

async function playSentence() {
  if (!props.text || ttsLoading.value) return;
  ttsLoading.value = true;
  try {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    }
    const response = await api.tts(props.text);
    if (!response.ok) throw new Error("TTS failed");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;
    audio.addEventListener("ended", () => URL.revokeObjectURL(url));
    await audio.play();
  } catch {
    /* swallow — the next click can retry. */
  } finally {
    ttsLoading.value = false;
  }
}
</script>

<template>
  <div
    class="my-2 ml-3 flex w-full max-w-prose flex-col gap-2 border-l-2 border-accent/40 bg-bg-elevated px-4 py-3 text-sm shadow-[0_1px_0_0_var(--color-border-subtle)] sm:ml-6"
  >
    <!-- Loading -->
    <template v-if="!state || state.status === 'loading'">
      <span
        class="inline-flex items-center gap-2 font-display text-fg-muted italic"
      >
        <span
          class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
        Translating…
      </span>
    </template>

    <!-- Error -->
    <template v-else-if="state.status === 'error'">
      <span class="font-display text-sm italic text-red-700 dark:text-red-300">
        Couldn't translate this sentence — {{ state.message }}.
      </span>
    </template>

    <!-- Result -->
    <template v-else-if="state.status === 'ok'">
      <div class="flex items-start justify-between gap-3">
        <p class="flex-1 font-display text-[15px] leading-snug text-fg">
          {{ state.data.translation }}
        </p>
        <!-- Play sentence audio -->
        <button
          type="button"
          class="inline-flex shrink-0 items-center justify-center rounded-md border border-border bg-bg-elevated p-1.5 text-fg-muted transition-colors hover:text-fg hover:bg-bg-sunken disabled:opacity-50"
          aria-label="Play sentence"
          :disabled="ttsLoading"
          @click.stop="playSentence"
        >
          <span
            v-if="ttsLoading"
            class="inline-block size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
          />
          <svg
            v-else
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
          >
            <path
              d="M3.5 5h2L8 3v10L5.5 11h-2V5z"
              fill="currentColor"
            />
            <path
              d="M10.5 5.5C11.5 6.3 12 7.1 12 8s-.5 1.7-1.5 2.5M12.5 4C14 5 14.5 6.5 14.5 8s-.5 3-2 4"
              stroke="currentColor"
              stroke-width="1.2"
              stroke-linecap="round"
            />
          </svg>
        </button>
      </div>
      <div class="flex items-center justify-between gap-3">
        <span
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          via {{ sourceLabel }}
        </span>
        <span
          v-if="state.data.cached"
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          cached
        </span>
      </div>
    </template>
  </div>
</template>

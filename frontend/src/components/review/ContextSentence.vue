<script setup lang="ts">
/**
 * The sentence a review word was met in, shown once the answer is out:
 * the word highlighted, where the sentence came from, and a button that
 * reads the whole sentence aloud.
 */
import { computed } from "vue";

import * as api from "@/api/client";
import { useTtsPlayer } from "@/composables/use-tts-player";

const props = defineProps<{
  sentence: string;
  word: string;
  source?: string | null;
}>();

const parts = computed(() => {
  const i = props.sentence.indexOf(props.word);
  if (i < 0) return { before: props.sentence, hit: "", after: "" };
  return {
    before: props.sentence.slice(0, i),
    hit: props.word,
    after: props.sentence.slice(i + props.word.length),
  };
});

const { loading, play: playAudio } = useTtsPlayer();

function play() {
  void playAudio(() => api.ttsSentence(props.sentence));
}
</script>

<template>
  <figure class="mx-auto mt-5 max-w-md border-t border-border-subtle pt-4 text-left">
    <p class="font-cn-serif text-lg leading-relaxed text-fg" data-testid="context-sentence">
      {{ parts.before }}<mark
        v-if="parts.hit"
        class="rounded-sm bg-accent/15 px-0.5 text-fg"
      >{{ parts.hit }}</mark>{{ parts.after }}
    </p>
    <figcaption
      class="mt-1.5 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
    >
      <button
        type="button"
        class="inline-flex size-6 items-center justify-center rounded-full border border-border text-fg-muted transition-colors hover:text-fg disabled:opacity-50"
        :disabled="loading"
        aria-label="Play sentence"
        @click="play"
      >
        <svg width="12" height="12" viewBox="0 0 28 28" fill="none" aria-hidden="true">
          <path d="M5 10h4l5-4v16l-5-4H5v-8z" fill="currentColor" />
          <path
            d="M18 9c2 2 2 8 0 10"
            stroke="currentColor"
            stroke-width="2.4"
            stroke-linecap="round"
          />
        </svg>
      </button>
      <span class="truncate normal-case tracking-normal">
        {{ source ? `from “${source}”` : "from your reading" }}
      </span>
    </figcaption>
  </figure>
</template>

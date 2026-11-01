<script setup lang="ts">
/** Top of the word popover: hanzi, pinyin, the play button and the HSK chip. */
import type { HskLevel, WordInfo } from "@/api/types";

import HskChip from "./HskChip.vue";

defineProps<{
  word: WordInfo;
  level: HskLevel | null | undefined;
  ttsLoading: boolean;
}>();

const emit = defineEmits<{
  (e: "play"): void;
}>();
</script>

<template>
  <div class="flex items-start justify-between gap-3">
    <div>
      <div class="font-cn-serif text-3xl leading-none text-fg">
        {{ word.text }}
      </div>
      <div v-if="word.pinyin" class="mt-1.5 font-sans text-sm text-fg-muted">
        {{ word.pinyin }}
      </div>
    </div>
    <div class="flex flex-col items-end gap-2">
      <div class="flex items-center gap-1.5">
        <button
          type="button"
          class="inline-flex items-center justify-center rounded-md border border-border bg-bg-elevated p-2 text-fg-muted transition-colors hover:text-fg hover:bg-bg-sunken disabled:opacity-50"
          aria-label="Play pronunciation"
          :disabled="ttsLoading"
          @click="emit('play')"
        >
          <span
            v-if="ttsLoading"
            class="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
          />
          <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3.5 5h2L8 3v10L5.5 11h-2V5z" fill="currentColor" />
            <path
              d="M10.5 5.5C11.5 6.3 12 7.1 12 8s-.5 1.7-1.5 2.5M12.5 4C14 5 14.5 6.5 14.5 8s-.5 3-2 4"
              stroke="currentColor"
              stroke-width="1.2"
              stroke-linecap="round"
            />
          </svg>
        </button>
      </div>
      <HskChip v-if="level" :level="level" />
    </div>
  </div>
</template>

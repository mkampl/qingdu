<script setup lang="ts">
/**
 * Parts of a token that is not a dictionary word (texts analysed before
 * phrases were split, or leftovers). It has no meaning or state of its
 * own; each part can be saved.
 */
import type { WordInfo } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { useUserWordsStore } from "@/stores/userWords";

defineProps<{
  parts: NonNullable<WordInfo["parts"]>;
}>();

const emit = defineEmits<{
  (e: "learn", part: string): void;
}>();

const auth = useAuthStore();
const userWords = useUserWordsStore();
</script>

<template>
  <div class="mt-4 border-t border-border-subtle pt-3 text-xs">
    <p class="font-mono uppercase tracking-wider text-fg-subtle">
      Parts
    </p>
    <ul class="mt-1.5 space-y-1">
      <li v-for="(p, i) in parts" :key="i" class="flex items-baseline gap-2">
        <span class="font-cn-serif text-base text-fg">{{ p.word }}</span>
        <span v-if="p.pinyin" class="shrink-0 text-fg-muted">{{ p.pinyin }}</span>
        <span v-if="p.meaning" class="min-w-0 flex-1 text-fg">{{ p.meaning }}</span>
        <button
          v-if="auth.isAuthed"
          type="button"
          class="ml-auto shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] text-fg-muted hover:bg-bg-sunken hover:text-fg disabled:opacity-60"
          :disabled="!!userWords.stateOf(p.word)"
          @click="emit('learn', p.word)"
        >
          {{ userWords.stateOf(p.word) ?? "Learn" }}
        </button>
      </li>
    </ul>
    <p class="mt-2 text-fg-subtle">
      Not a dictionary word, so it isn't saved as one.
    </p>
  </div>
</template>

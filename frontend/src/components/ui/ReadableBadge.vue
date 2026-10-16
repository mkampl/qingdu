<script setup lang="ts">
/**
 * "Readable" when the user knows 95 % of a text's running words, else
 * the share known and how many words are still missing to get there.
 */
defineProps<{ known: number; toUnlock: number; unlocked: boolean }>();
</script>

<template>
  <span
    v-if="unlocked"
    class="inline-flex items-center gap-0.5 rounded-full bg-emerald-500/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-emerald-600 dark:text-emerald-400"
    title="You know at least 95 % of this text's words"
  >
    <svg width="9" height="9" viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path
        d="M2 6.5l2.5 2.5L10 3"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
    readable
  </span>
  <span
    v-else
    :class="[
      'rounded-full px-2 py-0.5 font-mono text-[10px] tracking-wider',
      toUnlock > 0 && toUnlock <= 10 ? 'bg-accent/10 text-accent' : 'bg-bg-sunken text-fg-muted',
    ]"
    :title="
      toUnlock > 0
        ? `You know ${Math.floor(known * 100)}% — learn ${toUnlock} more word${toUnlock === 1 ? '' : 's'} to read it comfortably`
        : `You know ${Math.floor(known * 100)}% — readable once the words in review are learned`
    "
  >
    {{ Math.floor(known * 100) }}%<template v-if="toUnlock > 0"> · {{ toUnlock }} to go</template
    ><template v-else> · in review</template>
  </span>
</template>

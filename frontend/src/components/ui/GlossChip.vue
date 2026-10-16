<script setup lang="ts">
/** Provenance chip for a meaning: "Dict", a package name or a list name. */
import type { WordGloss } from "@/api/types";
import { glossLabel, glossTitle } from "@/utils/glosses";

defineProps<{ gloss: WordGloss }>();
</script>

<template>
  <span
    :class="[
      'inline-block max-w-[14rem] shrink-0 truncate rounded-full px-1.5 py-0.5 align-middle font-mono text-[9px] uppercase tracking-wider',
      gloss.source === 'dictionary'
        ? 'bg-bg-sunken text-fg-subtle'
        : 'bg-accent/15 text-accent',
    ]"
    :title="glossTitle(gloss)"
  >
    {{ glossLabel(gloss) }}
  </span>
</template>

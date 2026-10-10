<script setup lang="ts">
/**
 * Register tags ("bound form", "coll.", "literary" ...) that the
 * dictionary strips off a headline gloss. Rendered as small muted badges
 * after the headline so "male" reads cleanly but the learner still sees
 * that 男 is a bound form.
 */
defineProps<{ tags?: string[] | null }>();
</script>

<template>
  <span v-if="tags && tags.length" class="ml-1.5 inline-flex flex-wrap gap-1 align-middle">
    <span
      v-for="t in tags"
      :key="t"
      class="rounded-full bg-bg-sunken px-1.5 py-0.5 font-mono text-[9px] uppercase leading-none tracking-wider text-fg-subtle"
      :title="`Dictionary usage label: ${t}`"
    >
      {{ t }}
    </span>
  </span>
</template>

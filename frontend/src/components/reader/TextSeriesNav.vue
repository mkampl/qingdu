<script setup lang="ts">
/**
 * A saved text's place in its folder: at the top the folder path and
 * "2 / 6", at the bottom previous / next. Hidden for texts at the top
 * level.
 */
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import { useOpenSavedText } from "@/composables/use-open-saved-text";
import { useAnalysisStore } from "@/stores/analysis";

const props = defineProps<{ placement: "top" | "bottom" }>();

const analysis = useAnalysisStore();
const openSavedText = useOpenSavedText();
const busy = ref<"prev" | "next" | null>(null);

const series = computed(() => analysis.savedTextSeries);
const folderName = computed(() => series.value?.path.map((p) => p.name).join(" › ") ?? "");

async function go(which: "prev" | "next") {
  const id = which === "prev" ? series.value?.prev_id : series.value?.next_id;
  if (!id || busy.value) return;
  busy.value = which;
  try {
    if (await openSavedText(id)) window.scrollTo({ top: 0 });
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <nav
    v-if="series && props.placement === 'top'"
    class="mb-4 flex flex-wrap items-center gap-x-2 text-xs text-fg-muted"
    aria-label="Folder"
  >
    <RouterLink
      :to="{ path: '/texts', query: { folder: String(series.folder_id) } }"
      class="text-cn-serif inline-flex items-center gap-1 hover:text-accent"
    >
      <svg width="12" height="12" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <path
          d="M1.5 4V11.5h11V5H7L5.5 3h-4z"
          stroke="currentColor"
          stroke-width="1.2"
          stroke-linejoin="round"
        />
      </svg>
      {{ folderName }}
    </RouterLink>
    <span class="font-mono text-[10px] tabular-nums text-fg-subtle">
      {{ series.index }} / {{ series.count }}
    </span>
  </nav>

  <nav
    v-else-if="series && props.placement === 'bottom' && series.count > 1"
    class="mt-10 flex items-center justify-between gap-3 border-t border-border-subtle pt-5"
    aria-label="Previous and next text"
  >
    <button
      type="button"
      class="rounded-md border border-border px-3 py-1.5 text-sm text-fg-muted transition-colors hover:border-accent hover:text-accent disabled:invisible"
      :disabled="!series.prev_id || busy !== null"
      @click="go('prev')"
    >
      ← Previous
    </button>
    <span class="font-mono text-[10px] tabular-nums text-fg-subtle">
      {{ series.index }} / {{ series.count }}
    </span>
    <button
      type="button"
      class="rounded-md border border-border px-3 py-1.5 text-sm text-fg-muted transition-colors hover:border-accent hover:text-accent disabled:invisible"
      :disabled="!series.next_id || busy !== null"
      @click="go('next')"
    >
      Next →
    </button>
  </nav>
</template>

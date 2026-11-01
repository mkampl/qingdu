<script setup lang="ts">
/** Progress of an Anki export: audio check, generation, packaging, result. */
import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import Spinner from "@/components/ui/Spinner.vue";
import type { AnkiAudioProgress, AnkiExportPhase } from "@/composables/use-anki-export";

defineProps<{
  phase: AnkiExportPhase;
  progress: AnkiAudioProgress | null;
  error: string | null;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "retry"): void;
}>();
</script>

<template>
  <Modal
    :open="phase !== 'idle'"
    size="sm"
    :close-on-backdrop="phase === 'done' || phase === 'error'"
    @close="emit('close')"
  >
    <template #header>
      <h2 class="font-display text-xl font-medium tracking-tight text-fg">
        Anki export
      </h2>
    </template>

    <div class="space-y-4">
      <p
        v-if="phase === 'checking'"
        class="flex items-center gap-2 font-display italic text-fg-muted"
      >
        <Spinner size="sm" /> Checking audio cache…
      </p>

      <template v-else-if="phase === 'preparing'">
        <p class="flex items-center gap-2 font-display italic text-fg-muted">
          <Spinner size="sm" /> Generating audio (this can take a minute)…
        </p>
        <p
          v-if="progress"
          class="font-mono text-[11px] uppercase tracking-wider text-fg-subtle"
        >
          {{ progress.cached + progress.generated }} /
          {{ progress.total }} ready
        </p>
      </template>

      <p
        v-else-if="phase === 'downloading'"
        class="flex items-center gap-2 font-display italic text-fg-muted"
      >
        <Spinner size="sm" /> Packaging…
      </p>

      <template v-else-if="phase === 'done'">
        <p class="font-display text-base text-fg">
          Downloaded.
        </p>
        <p v-if="progress?.rate_limited" class="text-sm text-fg-muted">
          A few cards came through without audio because Google's TTS hit
          its rate limit. Try the export again later to fill those in.
        </p>
      </template>

      <template v-else-if="phase === 'error'">
        <p class="text-sm text-red-700 dark:text-red-300" role="alert">
          {{ error }}
        </p>
        <div class="flex items-center justify-end gap-2">
          <Button variant="ghost" size="sm" @click="emit('close')">
            Close
          </Button>
          <Button variant="primary" size="sm" @click="emit('retry')">
            Try again
          </Button>
        </div>
      </template>
    </div>
  </Modal>
</template>

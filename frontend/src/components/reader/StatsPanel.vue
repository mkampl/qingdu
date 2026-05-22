<script setup lang="ts">
import { computed } from "vue";

import type { AnalysisStatistics } from "@/api/types";
import { useSettingsStore } from "@/stores/settings";
import Button from "@/components/ui/Button.vue";

import LevelStrata from "./LevelStrata.vue";
import { levelNumber } from "./utils";

const props = defineProps<{
  statistics: AnalysisStatistics;
  canSave?: boolean;
  saved?: boolean;
  saving?: boolean;
  /** True when the analysis is linked to an existing saved-text record. */
  isUpdate?: boolean;
  /** True when the loaded saved-text content has been edited locally. */
  isEdited?: boolean;
}>();

const emit = defineEmits<{ (e: "save"): void }>();

const settings = useSettingsStore();

const distribution = computed(() =>
  settings.hskVersion === "old"
    ? props.statistics.hsk_distribution_old
    : props.statistics.hsk_distribution_new,
);
const totalHskWords = computed(() =>
  settings.hskVersion === "old"
    ? props.statistics.hsk_words_old
    : props.statistics.hsk_words_new,
);
const estimatedLevel = computed(() =>
  settings.hskVersion === "old"
    ? props.statistics.estimated_level_old
    : props.statistics.estimated_level_new,
);
const estimatedNumber = computed(() => levelNumber(estimatedLevel.value));
const coveragePct = computed(() => {
  const total = props.statistics.total_words || 1;
  return Math.round((totalHskWords.value / total) * 100);
});
</script>

<template>
  <aside
    class="flex flex-col gap-7 text-sm"
    aria-label="Composition and actions"
  >
    <!-- Estimated reading level — display-typography moment. -->
    <section>
      <p
        class="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Estimated level
      </p>
      <div class="mt-1.5 flex items-baseline gap-2">
        <span class="font-display text-4xl font-medium leading-none text-fg">
          {{ estimatedNumber !== null ? estimatedNumber : "—" }}
        </span>
        <span class="font-display text-base text-fg-muted">
          /
          {{ settings.hskVersion === "old" ? "6" : "9" }}
        </span>
        <span
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          {{ settings.hskVersion === "old" ? "old HSK" : "new HSK" }}
        </span>
      </div>
    </section>

    <!-- Composition strata bar -->
    <section>
      <p
        class="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Composition
      </p>
      <LevelStrata
        :distribution="distribution"
        :total-hsk-words="totalHskWords"
        :estimated-level="estimatedLevel"
      />
    </section>

    <!-- Counts grid -->
    <section
      class="grid grid-cols-3 gap-x-3 gap-y-1 border-t border-border-subtle pt-5"
    >
      <div>
        <p class="font-display text-2xl font-medium leading-none text-fg">
          {{ statistics.total_words.toLocaleString() }}
        </p>
        <p class="mt-1 font-mono text-[9px] uppercase tracking-wider text-fg-subtle">
          Tokens
        </p>
      </div>
      <div>
        <p class="font-display text-2xl font-medium leading-none text-fg">
          {{ statistics.total_characters.toLocaleString() }}
        </p>
        <p class="mt-1 font-mono text-[9px] uppercase tracking-wider text-fg-subtle">
          Chars
        </p>
      </div>
      <div>
        <p class="font-display text-2xl font-medium leading-none text-fg">
          {{ coveragePct }}<span class="text-base text-fg-muted">%</span>
        </p>
        <p class="mt-1 font-mono text-[9px] uppercase tracking-wider text-fg-subtle">
          HSK
        </p>
      </div>
    </section>

    <!-- HSK colour legend — opt-in via Settings. Two columns of swatches so
         it stays compact in the margin panel. -->
    <section
      v-if="settings.showLegend"
      class="border-t border-border-subtle pt-5"
    >
      <p
        class="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Levels
      </p>
      <ul class="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        <li
          v-for="n in settings.hskVersion === 'old' ? 6 : 9"
          :key="n"
          class="flex items-center gap-2"
        >
          <span
            class="inline-block size-2.5 rounded-sm"
            :style="{
              backgroundColor: `color-mix(in oklch, var(--color-hsk-${n}), transparent 40%)`,
              boxShadow: `inset 0 0 0 1px color-mix(in oklch, var(--color-hsk-${n}), transparent 10%)`,
            }"
          />
          <span class="text-fg-muted">HSK {{ n }}</span>
        </li>
      </ul>
    </section>

    <!-- Save action — label and disabled state reflect:
           - anonymous           -> 'Sign in to save'
           - fresh analysis      -> 'Save text' (primary)
           - just saved          -> 'Saved' (disabled)
           - loaded saved text   -> 'Saved' (disabled)
           - loaded + edited     -> 'Update' (primary, enabled)
    -->
    <section class="border-t border-border-subtle pt-5">
      <Button
        :variant="canSave ? 'primary' : 'secondary'"
        full
        :loading="saving"
        :disabled="!canSave || (saved && !isEdited)"
        @click="emit('save')"
      >
        <template v-if="!canSave">Sign in to save</template>
        <template v-else-if="isEdited">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path
              d="M2 9.5l8-8M2 9.5l3 0M2 9.5l0-3"
              stroke="currentColor"
              stroke-width="1.4"
              stroke-linecap="round"
            />
          </svg>
          Update
        </template>
        <template v-else-if="saved">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path
              d="M2 6.5l3 3 5-7"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          Saved
        </template>
        <template v-else>Save text</template>
      </Button>
      <p
        class="mt-2 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
      >
        {{
          !canSave
            ? "Texts you save show up here later"
            : isEdited
              ? "Save your edits to this text"
              : isUpdate
                ? "In your library"
                : "Adds to your library"
        }}
      </p>
    </section>
  </aside>
</template>

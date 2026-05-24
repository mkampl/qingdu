<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";

import * as api from "@/api/client";
import type { ConvertDirection } from "@/api/client";
import Button from "@/components/ui/Button.vue";
import GlossaryPicker from "@/components/reader/GlossaryPicker.vue";
import { submitShortcutLabel } from "@/utils/platform";

const props = defineProps<{
  modelValue: string;
  loading?: boolean;
  collapsed?: boolean;
  hasResult?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
  (e: "analyze"): void;
  (e: "import-url"): void;
  (e: "expand"): void;
  (e: "clear"): void;
}>();

const textareaRef = ref<HTMLTextAreaElement | null>(null);

const characterCount = computed(() => props.modelValue.length);
const wordCountEstimate = computed(() =>
  Array.from(props.modelValue).filter((c) => /[一-鿿]/.test(c)).length,
);

async function autoResize() {
  await nextTick();
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 540)}px`;
}

onMounted(autoResize);
watch(() => props.modelValue, autoResize);

watch(
  () => props.collapsed,
  (collapsed) => {
    if (!collapsed) nextTick(() => textareaRef.value?.focus());
  },
);

function onInput(e: Event) {
  emit("update:modelValue", (e.target as HTMLTextAreaElement).value);
}

function onKeydown(e: KeyboardEvent) {
  // Cmd/Ctrl + Enter -> analyze (a writer's keyboard shortcut)
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    emit("analyze");
  }
}

// --- Trad ⇄ Simp conversion -----------------------------------------------
//
// Two manual buttons + a passive suggestion banner. We auto-detect on input
// (debounced 600ms) and surface a one-click "Convert to Simplified?" prompt
// only when the heuristic is confident. The HSK vocab + jieba expect
// Simplified so the suggestion always nudges toward s.

const detectedScript = ref<"simplified" | "traditional" | "unknown">("unknown");
const detectConfidence = ref(0);
const showSuggestion = computed(
  () => detectedScript.value === "traditional" && detectConfidence.value >= 0.1,
);
const converting = ref(false);
let detectTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleDetect() {
  if (detectTimer) clearTimeout(detectTimer);
  if (!props.modelValue.trim()) {
    detectedScript.value = "unknown";
    detectConfidence.value = 0;
    return;
  }
  detectTimer = setTimeout(async () => {
    try {
      const r = await api.detectScript(props.modelValue);
      detectedScript.value = r.script;
      detectConfidence.value = r.confidence;
    } catch {
      // Detection is a nicety; never gate on it.
    }
  }, 600);
}

watch(() => props.modelValue, scheduleDetect);

async function convert(direction: ConvertDirection) {
  if (!props.modelValue.trim() || converting.value) return;
  converting.value = true;
  try {
    const r = await api.convertScript(props.modelValue, direction);
    emit("update:modelValue", r.converted);
    // After a manual conversion the suggestion is no longer relevant.
    detectedScript.value = direction === "t2s" ? "simplified" : "traditional";
    detectConfidence.value = 1;
  } catch {
    /* best effort */
  } finally {
    converting.value = false;
  }
}
</script>

<template>
  <!-- Collapsed state: a thin marginalia stripe at the top of the reading column.
       The textarea contents are summarised; tapping expands the full editor. -->
  <div
    v-if="collapsed && hasResult"
    class="group flex items-center gap-3 border-b border-border-subtle py-2"
  >
    <button
      type="button"
      class="-ml-1 inline-flex items-center gap-2 rounded-md px-2 py-1 text-xs font-medium text-fg-muted transition-colors hover:text-fg hover:bg-bg-sunken"
      @click="emit('expand')"
    >
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path
          d="M2 9.5l8-8M2 9.5l3 0M2 9.5l0-3"
          stroke="currentColor"
          stroke-width="1.2"
          stroke-linecap="round"
        />
      </svg>
      Edit text
    </button>
    <span class="h-3 w-px bg-border-subtle" aria-hidden="true" />
    <button
      type="button"
      class="inline-flex items-center gap-2 rounded-md px-2 py-1 text-xs font-medium text-fg-muted transition-colors hover:text-fg hover:bg-bg-sunken"
      title="Discard the current text and start fresh"
      @click="emit('clear')"
    >
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path
          d="M6 2v8M2 6h8"
          stroke="currentColor"
          stroke-width="1.4"
          stroke-linecap="round"
        />
      </svg>
      New text
    </button>
    <span
      class="ml-auto font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
    >
      {{ characterCount }} chars · {{ wordCountEstimate }} hanzi
    </span>
  </div>

  <!-- Expanded editor state: generous textarea on cream/elevated surface with
       a hairline rule baseline (writer's-paper feel) and serif placeholder. -->
  <section
    v-else
    class="mb-8"
    aria-label="Enter Chinese text"
  >
    <div class="mb-3 flex items-baseline justify-between gap-2">
      <h2 class="font-display text-xl font-medium tracking-tight text-fg">
        <span class="text-cn-serif">新文本</span>
        <span
          class="ml-2 align-[0.04em] font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-fg-subtle"
        >
          New text
        </span>
      </h2>
      <button
        v-if="modelValue"
        type="button"
        class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle transition-colors hover:text-accent"
        @click="emit('clear')"
      >
        Clear
      </button>
    </div>

    <!-- Auto-detect Traditional → suggest conversion. Lives above the
         textarea so it's visible without scrolling past the keyboard on
         mobile. Dismissible by acting on it (Convert) or by typing more
         (which re-runs the detection). -->
    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
    >
      <div
        v-if="showSuggestion"
        class="mb-2 flex items-center justify-between gap-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
      >
        <p class="leading-relaxed">
          <span class="font-medium">Looks like Traditional Chinese.</span>
          The HSK matcher works on Simplified — convert for accurate analysis?
        </p>
        <button
          type="button"
          class="shrink-0 rounded-md border border-amber-400 bg-amber-100 px-2.5 py-1 font-medium text-amber-900 transition-colors hover:bg-amber-200 disabled:opacity-50 dark:border-amber-700 dark:bg-amber-900/40 dark:text-amber-100 dark:hover:bg-amber-900/60"
          :disabled="converting"
          @click="convert('t2s')"
        >
          {{ converting ? "Converting…" : "Convert to Simplified" }}
        </button>
      </div>
    </Transition>

    <div
      class="relative overflow-hidden rounded-md border border-border bg-bg-elevated shadow-sm"
    >
      <textarea
        ref="textareaRef"
        :value="modelValue"
        rows="6"
        class="text-cn-serif relative block w-full resize-none bg-transparent px-5 py-4 text-[19px] leading-[1.8em] text-fg outline-none placeholder:font-cn-serif placeholder:italic placeholder:text-fg-subtle"
        placeholder="你好。在这里输入中文..."
        autocomplete="off"
        spellcheck="false"
        @input="onInput"
        @keydown="onKeydown"
      />

      <!-- Bottom rail: counters + import + analyze action -->
      <div
        class="flex items-center justify-between gap-3 border-t border-border-subtle bg-bg-sunken/70 px-4 py-2.5"
      >
        <span
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          {{ characterCount }} chars · {{ wordCountEstimate }} hanzi
          <span class="mx-1.5 text-fg-subtle/40">·</span>
          <kbd
            class="rounded border border-border-subtle bg-bg-elevated px-1.5 py-0.5 font-sans text-[10px] font-medium tracking-normal normal-case text-fg-muted"
          >{{ submitShortcutLabel }}</kbd>
          to analyze
        </span>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-fg-muted transition-colors hover:text-fg hover:bg-bg-sunken"
            title="Import from URL, EPUB, or PDF"
            @click="emit('import-url')"
          >
            <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
              <path
                d="M4 3h4v4M7.5 3.5L3 8M2 6v3h3"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            Import
          </button>
          <!-- Phase #99 — Glossary picker. Hides itself when the user has no
               glossary-flagged lists yet. -->
          <GlossaryPicker />
          <!-- Script converters. Hidden on the narrowest screens to keep
               the row from wrapping; the auto-detect banner covers the
               most-common case there anyway. -->
          <button
            type="button"
            class="hidden items-center gap-1 rounded-md px-2 py-1 font-mono text-[11px] font-medium text-fg-muted transition-colors hover:text-fg hover:bg-bg-sunken disabled:opacity-50 sm:inline-flex"
            title="Convert Traditional → Simplified"
            :disabled="!modelValue.trim() || converting"
            @click="convert('t2s')"
          >
            繁 → 简
          </button>
          <button
            type="button"
            class="hidden items-center gap-1 rounded-md px-2 py-1 font-mono text-[11px] font-medium text-fg-muted transition-colors hover:text-fg hover:bg-bg-sunken disabled:opacity-50 sm:inline-flex"
            title="Convert Simplified → Traditional"
            :disabled="!modelValue.trim() || converting"
            @click="convert('s2t')"
          >
            简 → 繁
          </button>
        <Button
          variant="primary"
          size="sm"
          :loading="loading"
          :disabled="!modelValue.trim()"
          @click="emit('analyze')"
        >
          <template v-if="!loading">
            Analyze
            <svg
              class="ml-0.5"
              width="11"
              height="11"
              viewBox="0 0 11 11"
              fill="none"
            >
              <path
                d="M2 5.5h7M6 2.5l3 3-3 3"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </template>
          <template v-else>Analyzing…</template>
        </Button>
        </div>
      </div>
    </div>
  </section>
</template>

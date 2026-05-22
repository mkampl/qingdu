<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";

import Button from "@/components/ui/Button.vue";

const props = defineProps<{
  modelValue: string;
  loading?: boolean;
  collapsed?: boolean;
  hasResult?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
  (e: "analyze"): void;
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
    <span
      class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
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

    <div
      class="relative overflow-hidden rounded-md border border-border bg-bg-elevated shadow-sm"
    >
      <!-- Faint horizontal ruled lines using a repeating gradient, like
           writer's paper. Pure CSS, no images. -->
      <div
        class="pointer-events-none absolute inset-0 opacity-[0.06]"
        :style="{
          backgroundImage:
            'repeating-linear-gradient(to bottom, transparent 0, transparent calc(1.8em - 1px), var(--color-fg-muted) calc(1.8em - 1px), var(--color-fg-muted) 1.8em)',
        }"
        aria-hidden="true"
      />

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

      <!-- Bottom rail: counters + analyze action -->
      <div
        class="flex items-center justify-between gap-3 border-t border-border-subtle bg-bg-sunken/70 px-4 py-2.5"
      >
        <span
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          {{ characterCount }} chars · {{ wordCountEstimate }} hanzi
          <span class="mx-1.5 text-fg-subtle/40">·</span>
          <kbd
            class="rounded border border-border-subtle bg-bg-elevated px-1 py-0.5 font-mono text-[9px] text-fg-muted"
          >⌘⏎</kbd>
          to analyze
        </span>
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
  </section>
</template>

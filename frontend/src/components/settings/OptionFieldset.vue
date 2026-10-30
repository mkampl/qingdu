<script setup lang="ts" generic="T extends string">
// A radio group: one bordered card per option with a label and a hint
// line; the selected card is highlighted. The default slot is the legend.
defineProps<{
  options: { value: T; label: string; hint: string }[];
  // Two cards per row instead of a stacked list.
  grid?: boolean;
}>();

const model = defineModel<T>({ required: true });
</script>

<template>
  <fieldset>
    <legend
      class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
    >
      <slot />
    </legend>
    <div :class="grid ? 'grid grid-cols-2 gap-2' : 'space-y-2'">
      <label
        v-for="opt in options"
        :key="opt.value"
        class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
        :class="{
          'border-accent bg-bg-sunken': model === opt.value,
        }"
      >
        <input
          v-model="model"
          type="radio"
          :value="opt.value"
          class="mt-1 accent-accent"
        />
        <span class="flex-1">
          <span class="block font-display text-base text-fg">
            {{ opt.label }}
          </span>
          <span class="block text-xs text-fg-muted">{{ opt.hint }}</span>
        </span>
      </label>
    </div>
  </fieldset>
</template>

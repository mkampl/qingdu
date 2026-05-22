<script setup lang="ts">
const props = defineProps<{
  modelValue: string;
  type?: "text" | "password" | "email";
  placeholder?: string;
  label?: string;
  hint?: string;
  error?: string | null;
  autofocus?: boolean;
  required?: boolean;
  autocomplete?: string;
  id?: string;
}>();

defineEmits<{ (e: "update:modelValue", value: string): void }>();

const inputId = props.id ?? `input-${Math.random().toString(36).slice(2, 8)}`;
</script>

<template>
  <label :for="inputId" class="block">
    <span
      v-if="label"
      class="mb-1.5 block text-sm font-medium text-fg"
    >
      {{ label }}
      <span v-if="required" class="text-red-500" aria-hidden="true">*</span>
    </span>
    <input
      :id="inputId"
      :type="type ?? 'text'"
      :value="modelValue"
      :placeholder="placeholder"
      :autofocus="autofocus"
      :required="required"
      :autocomplete="autocomplete"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="hint || error ? `${inputId}-hint` : undefined"
      class="block w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-fg placeholder:text-fg-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
      @input="
        $emit(
          'update:modelValue',
          ($event.target as HTMLInputElement).value,
        )
      "
    />
    <span
      v-if="hint || error"
      :id="`${inputId}-hint`"
      class="mt-1 block text-xs"
      :class="error ? 'text-red-600 dark:text-red-400' : 'text-fg-muted'"
    >
      {{ error ?? hint }}
    </span>
  </label>
</template>

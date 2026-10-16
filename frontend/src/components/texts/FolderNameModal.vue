<script setup lang="ts">
/** Name a new folder, or rename one. */
import { ref, watch } from "vue";

import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import TextInput from "@/components/ui/TextInput.vue";

const props = defineProps<{
  open: boolean;
  title: string;
  initial?: string;
  busy?: boolean;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "submit", name: string): void;
}>();

const name = ref("");
watch(
  () => props.open,
  (open) => {
    if (open) name.value = props.initial ?? "";
  },
);

function submit() {
  const n = name.value.trim();
  if (n) emit("submit", n.slice(0, 120));
}
</script>

<template>
  <Modal :open="open" :title="title" size="sm" close-on-backdrop @close="emit('close')">
    <form @submit.prevent="submit">
      <TextInput v-model="name" label="Name" autofocus autocomplete="off" />
    </form>
    <template #footer>
      <div class="flex justify-end gap-2">
        <Button variant="ghost" size="sm" @click="emit('close')">Cancel</Button>
        <Button variant="primary" size="sm" :loading="busy" :disabled="!name.trim()" @click="submit">
          Save
        </Button>
      </div>
    </template>
  </Modal>
</template>

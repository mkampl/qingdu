<script setup lang="ts">
import { ref, watch } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useToastStore } from "@/stores/toast";

import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import TextInput from "@/components/ui/TextInput.vue";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{
  (e: "close"): void;
  /** Fires with the extracted article body once the user confirms. */
  (e: "import", payload: { content: string; title: string | null }): void;
}>();

const auth = useAuthStore();
const authModals = useAuthModalsStore();
const toasts = useToastStore();

const url = ref("");
const fetching = ref(false);
const error = ref<string | null>(null);
const preview = ref<api.ExtractedArticle | null>(null);

watch(
  () => props.open,
  (open) => {
    if (open) {
      url.value = "";
      error.value = null;
      preview.value = null;
    }
  },
);

async function fetchAndPreview(e: Event) {
  e.preventDefault();
  if (fetching.value) return;
  if (!auth.isAuthed) {
    emit("close");
    authModals.openLogin();
    toasts.info("Sign in to import articles.");
    return;
  }
  const target = url.value.trim();
  if (!target) {
    error.value = "Paste a URL first.";
    return;
  }
  if (!/^https?:\/\//i.test(target)) {
    error.value = "URL must start with http:// or https://";
    return;
  }
  fetching.value = true;
  error.value = null;
  try {
    preview.value = await api.extractArticle(target);
  } catch (e) {
    error.value =
      e instanceof ApiError ? e.message : "Couldn't extract that article.";
  } finally {
    fetching.value = false;
  }
}

function importNow() {
  if (!preview.value) return;
  emit("import", {
    content: preview.value.content,
    title: preview.value.title,
  });
  emit("close");
}

function back() {
  preview.value = null;
}

function snippet(text: string, len = 240) {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > len ? `${clean.slice(0, len)}…` : clean;
}
</script>

<template>
  <Modal
    :open="open"
    size="md"
    close-on-backdrop
    @close="emit('close')"
  >
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Import from URL
        </h2>
        <span
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          Any article
        </span>
      </div>
    </template>

    <!-- Step 1: paste URL -->
    <form v-if="!preview" class="space-y-4" @submit="fetchAndPreview">
      <p class="font-display text-sm italic leading-relaxed text-fg-muted">
        Paste the link to any Chinese article — Wikipedia, a news story, a
        blog post — and we'll fetch just the article body, no navigation or
        ads.
      </p>
      <TextInput
        v-model="url"
        label="Article URL"
        placeholder="https://zh.wikipedia.org/wiki/茶"
        autocomplete="off"
        autofocus
        required
      />
      <p
        v-if="error"
        class="text-sm text-red-700 dark:text-red-300"
        role="alert"
      >
        {{ error }}
      </p>
      <div class="flex items-center justify-end gap-2">
        <Button
          variant="ghost"
          size="sm"
          type="button"
          @click="emit('close')"
        >
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          type="submit"
          :loading="fetching"
          :disabled="!url.trim()"
        >
          Fetch
        </Button>
      </div>
    </form>

    <!-- Step 2: preview + confirm -->
    <div v-else class="space-y-4">
      <p
        class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
      >
        Preview
      </p>
      <div class="rounded-lg border border-border-subtle bg-bg-sunken p-4">
        <p
          v-if="preview.title"
          class="text-cn-serif text-lg font-medium leading-snug text-fg"
        >
          {{ preview.title }}
        </p>
        <p
          v-if="preview.byline"
          class="mt-0.5 font-display text-xs italic text-fg-muted"
        >
          by {{ preview.byline }}
        </p>
        <p
          class="text-cn-serif mt-3 text-sm leading-relaxed text-fg-muted line-clamp-4"
        >
          {{ snippet(preview.content) }}
        </p>
        <div class="mt-3 flex items-center gap-2">
          <span
            class="rounded-full bg-bg-elevated px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-fg-muted"
          >
            {{ preview.char_count.toLocaleString() }} chars
          </span>
          <span
            class="truncate font-mono text-[10px] text-fg-subtle"
            :title="preview.url"
          >
            {{ preview.url }}
          </span>
        </div>
      </div>
      <div class="flex items-center justify-end gap-2">
        <Button variant="ghost" size="sm" @click="back">Try a different URL</Button>
        <Button variant="primary" size="sm" @click="importNow">
          Use this text
        </Button>
      </div>
    </div>
  </Modal>
</template>

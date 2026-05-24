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

type Mode = "url" | "file" | "scan";

const mode = ref<Mode>("url");
const url = ref("");
const file = ref<File | null>(null);
const fetching = ref(false);
const error = ref<string | null>(null);
const preview = ref<api.ExtractedArticle | null>(null);

// Scan (OCR) state — separate from `file` because the workflow is different
// (preview the image, run OCR, then surface the recognised text).
const scanFile = ref<File | null>(null);
const scanPreviewUrl = ref<string | null>(null);
const ocrRunning = ref(false);
const ocrProgress = ref(0); // 0-1, from tesseract.js progress events

watch(
  () => props.open,
  (open) => {
    if (open) {
      mode.value = "url";
      url.value = "";
      file.value = null;
      error.value = null;
      preview.value = null;
      resetScan();
    } else {
      resetScan();
    }
  },
);

function resetScan() {
  if (scanPreviewUrl.value) URL.revokeObjectURL(scanPreviewUrl.value);
  scanFile.value = null;
  scanPreviewUrl.value = null;
  ocrRunning.value = false;
  ocrProgress.value = 0;
}

function onFilePick(e: Event) {
  const input = e.target as HTMLInputElement;
  file.value = input.files?.[0] ?? null;
  error.value = null;
}

async function uploadAndPreview() {
  if (fetching.value || !file.value) return;
  if (!auth.isAuthed) {
    emit("close");
    authModals.openLogin();
    toasts.info("Sign in to import files.");
    return;
  }
  fetching.value = true;
  error.value = null;
  try {
    preview.value = await api.extractFile(file.value);
  } catch (e) {
    error.value =
      e instanceof ApiError ? e.message : "Couldn't read that file.";
  } finally {
    fetching.value = false;
  }
}

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

// --- Scan / OCR ------------------------------------------------------------
//
// tesseract.js is ~2 MB compressed plus a ~5 MB chi_sim language model
// fetched on first use. We import it dynamically the first time the user
// asks to OCR — the main app bundle stays slim for everyone else.

function onScanFilePick(e: Event) {
  const input = e.target as HTMLInputElement;
  const picked = input.files?.[0] ?? null;
  if (scanPreviewUrl.value) URL.revokeObjectURL(scanPreviewUrl.value);
  scanFile.value = picked;
  scanPreviewUrl.value = picked ? URL.createObjectURL(picked) : null;
  error.value = null;
}

async function runOcr() {
  if (!scanFile.value || ocrRunning.value) return;
  ocrRunning.value = true;
  error.value = null;
  ocrProgress.value = 0;
  try {
    // Dynamic import keeps tesseract out of the main bundle.
    const { createWorker } = await import("tesseract.js");
    const worker = await createWorker("chi_sim", 1, {
      logger: (m: { status?: string; progress?: number }) => {
        // 'recognizing text' is the main pass; show progress for that.
        if (m.status === "recognizing text" && typeof m.progress === "number") {
          ocrProgress.value = m.progress;
        }
      },
    });
    const { data } = await worker.recognize(scanFile.value);
    await worker.terminate();
    const text = (data.text || "").trim();
    if (!text) {
      error.value =
        "Couldn't read any Chinese characters from that image. Try a sharper photo.";
      return;
    }
    // Synthesize the same shape the URL/file extractors return so the
    // preview step doesn't know it came from OCR.
    preview.value = {
      url: `scan://${scanFile.value.name}`,
      title: null,
      byline: null,
      excerpt: text.slice(0, 300) || null,
      content: text,
      char_count: text.length,
    };
  } catch (e) {
    error.value =
      e instanceof Error ? `OCR failed: ${e.message}` : "OCR failed.";
  } finally {
    ocrRunning.value = false;
  }
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
          Import text
        </h2>
        <span
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          URL · EPUB · PDF
        </span>
      </div>
    </template>

    <!-- Mode tabs — sit at the top of every step so the user can switch
         without losing the preview if they've already fetched something. -->
    <div
      v-if="!preview"
      class="mb-4 flex gap-1 border-b border-border-subtle"
      role="tablist"
    >
      <button
        type="button"
        role="tab"
        :aria-selected="mode === 'url'"
        class="-mb-px border-b-2 px-3 py-1.5 text-sm font-medium transition-colors"
        :class="
          mode === 'url'
            ? 'border-accent text-fg'
            : 'border-transparent text-fg-muted hover:text-fg'
        "
        @click="mode = 'url'; error = null"
      >
        URL
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="mode === 'file'"
        class="-mb-px border-b-2 px-3 py-1.5 text-sm font-medium transition-colors"
        :class="
          mode === 'file'
            ? 'border-accent text-fg'
            : 'border-transparent text-fg-muted hover:text-fg'
        "
        @click="mode = 'file'; error = null"
      >
        EPUB / PDF
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="mode === 'scan'"
        class="-mb-px border-b-2 px-3 py-1.5 text-sm font-medium transition-colors"
        :class="
          mode === 'scan'
            ? 'border-accent text-fg'
            : 'border-transparent text-fg-muted hover:text-fg'
        "
        @click="mode = 'scan'; error = null"
      >
        Scan
      </button>
    </div>

    <!-- Step 1a: paste URL -->
    <form
      v-if="!preview && mode === 'url'"
      class="space-y-4"
      @submit="fetchAndPreview"
    >
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

    <!-- Step 1b: pick a file -->
    <div v-if="!preview && mode === 'file'" class="space-y-4">
      <p class="font-display text-sm italic leading-relaxed text-fg-muted">
        Drop an EPUB or PDF — we'll pull out the text body, drop images and
        page furniture, and import the first ~50 000 characters. Scanned
        PDFs need OCR (coming soon).
      </p>

      <label
        class="flex cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed border-border-subtle bg-bg-elevated px-4 py-8 text-center transition-colors hover:border-accent hover:bg-bg-sunken"
      >
        <input
          type="file"
          accept=".epub,.pdf,application/epub+zip,application/pdf"
          class="sr-only"
          @change="onFilePick"
        />
        <svg
          width="22"
          height="22"
          viewBox="0 0 22 22"
          fill="none"
          class="mb-2 text-fg-subtle"
          aria-hidden="true"
        >
          <path
            d="M11 14V4M6 9l5-5 5 5M3 17h16M3 17v3h16v-3"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <p v-if="file" class="font-display text-sm text-fg">
          {{ file.name }}
          <span class="ml-1 font-mono text-[10px] text-fg-subtle">
            {{ (file.size / 1024).toFixed(0) }} KB
          </span>
        </p>
        <p v-else class="font-display text-sm text-fg-muted">
          Click to pick a file
          <span class="block mt-0.5 font-mono text-[10px] text-fg-subtle">
            .epub, .pdf · max 10 MB
          </span>
        </p>
      </label>

      <p
        v-if="error"
        class="text-sm text-red-700 dark:text-red-300"
        role="alert"
      >
        {{ error }}
      </p>

      <div class="flex items-center justify-end gap-2">
        <Button variant="ghost" size="sm" type="button" @click="emit('close')">
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          type="button"
          :loading="fetching"
          :disabled="!file"
          @click="uploadAndPreview"
        >
          Import
        </Button>
      </div>
    </div>

    <!-- Step 1c: scan an image -->
    <div v-if="!preview && mode === 'scan'" class="space-y-4">
      <p class="font-display text-sm italic leading-relaxed text-fg-muted">
        Snap a page of a textbook, sign, or menu — we'll OCR Simplified
        Chinese in your browser (no upload). First scan downloads the
        language model (~5 MB); subsequent scans are instant.
      </p>

      <label
        class="flex cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed border-border-subtle bg-bg-elevated px-4 py-6 text-center transition-colors hover:border-accent hover:bg-bg-sunken"
      >
        <input
          type="file"
          accept="image/*"
          capture="environment"
          class="sr-only"
          @change="onScanFilePick"
        />
        <template v-if="scanPreviewUrl">
          <img
            :src="scanPreviewUrl"
            alt="Selected image"
            class="mx-auto mb-2 max-h-40 rounded border border-border-subtle object-contain"
          />
          <p class="font-display text-xs text-fg-muted">
            {{ scanFile?.name }} · tap to replace
          </p>
        </template>
        <template v-else>
          <svg
            width="22"
            height="22"
            viewBox="0 0 22 22"
            fill="none"
            class="mb-2 text-fg-subtle"
            aria-hidden="true"
          >
            <path
              d="M3 6h3l1.5-2h7L16 6h3v12H3V6z"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linejoin="round"
            />
            <circle
              cx="11"
              cy="12"
              r="3"
              stroke="currentColor"
              stroke-width="1.6"
            />
          </svg>
          <p class="font-display text-sm text-fg-muted">
            Tap to pick or capture an image
            <span class="block mt-0.5 font-mono text-[10px] text-fg-subtle">
              jpg, png, webp · max ~8 MB
            </span>
          </p>
        </template>
      </label>

      <div
        v-if="ocrRunning"
        class="space-y-1.5 rounded-md border border-border-subtle bg-bg-elevated px-3 py-2"
      >
        <div class="flex items-center justify-between">
          <p
            class="font-mono text-[10px] uppercase tracking-wider text-fg-muted"
          >
            Reading…
          </p>
          <p class="font-mono text-[10px] tabular-nums text-fg-subtle">
            {{ Math.round(ocrProgress * 100) }}%
          </p>
        </div>
        <div class="h-[3px] w-full overflow-hidden rounded-full bg-bg-sunken">
          <div
            class="h-full rounded-full bg-accent transition-[width] duration-150"
            :style="{ width: `${ocrProgress * 100}%` }"
          />
        </div>
      </div>

      <p
        v-if="error"
        class="text-sm text-red-700 dark:text-red-300"
        role="alert"
      >
        {{ error }}
      </p>

      <div class="flex items-center justify-end gap-2">
        <Button variant="ghost" size="sm" type="button" @click="emit('close')">
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          type="button"
          :loading="ocrRunning"
          :disabled="!scanFile"
          @click="runOcr"
        >
          Recognize text
        </Button>
      </div>
    </div>

    <!-- Step 2: preview + confirm -->
    <div v-if="preview" class="space-y-4">
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

<script setup lang="ts">
/**
 * Pick a folder to move a text or a folder into: the folder tree with the
 * top level first. When a folder is being moved, it and its subfolders
 * can't be picked.
 */
import { computed } from "vue";

import type { TextFolder } from "@/api/types";
import Modal from "@/components/ui/Modal.vue";
import { childFolders, folderAndBelow } from "@/utils/text-folders";

const props = defineProps<{
  open: boolean;
  title: string;
  folders: TextFolder[];
  /** Where the item is now (shown, not pickable). */
  currentId: number | null;
  /** Folder being moved: it and everything below it are not pickable. */
  movingFolderId?: number | null;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "pick", folderId: number | null): void;
}>();

const blocked = computed(() =>
  props.movingFolderId != null
    ? folderAndBelow(props.folders, props.movingFolderId)
    : new Set<number>(),
);

// The tree flattened with its depth, for an indented list.
const rows = computed(() => {
  const out: { folder: TextFolder; depth: number }[] = [];
  const walk = (parentId: number | null, depth: number) => {
    for (const f of childFolders(props.folders, parentId)) {
      out.push({ folder: f, depth });
      walk(f.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
});
</script>

<template>
  <Modal :open="open" :title="title" size="sm" close-on-backdrop @close="emit('close')">
    <ul class="max-h-[60vh] overflow-y-auto rounded-md border border-border-subtle">
      <li>
        <button
          type="button"
          class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-bg-sunken disabled:cursor-default disabled:opacity-50"
          :disabled="currentId === null"
          @click="emit('pick', null)"
        >
          <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
            Top level
          </span>
          <span v-if="currentId === null" class="ml-auto text-xs text-fg-subtle">here now</span>
        </button>
      </li>
      <li v-for="row in rows" :key="row.folder.id" class="border-t border-border-subtle">
        <button
          type="button"
          class="flex w-full items-center gap-2 py-2 pr-3 text-left text-sm text-fg hover:bg-bg-sunken disabled:cursor-default disabled:opacity-50"
          :style="{ paddingLeft: `${0.75 + row.depth * 1.1}rem` }"
          :disabled="row.folder.id === currentId || blocked.has(row.folder.id)"
          @click="emit('pick', row.folder.id)"
        >
          <svg width="13" height="13" viewBox="0 0 14 14" fill="none" aria-hidden="true" class="shrink-0 text-fg-subtle">
            <path
              d="M1.5 4V11.5h11V5H7L5.5 3h-4z"
              stroke="currentColor"
              stroke-width="1.2"
              stroke-linejoin="round"
            />
          </svg>
          <span class="text-cn-serif truncate">{{ row.folder.name }}</span>
          <span v-if="row.folder.id === currentId" class="ml-auto text-xs text-fg-subtle">
            here now
          </span>
        </button>
      </li>
    </ul>
  </Modal>
</template>

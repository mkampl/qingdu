import { defineStore } from "pinia";
import { ref } from "vue";

import * as api from "@/api/client";
import type { TextFolder } from "@/api/types";

/**
 * The user's text folders, and the folder open in the Texts view. A text
 * saved from the reader goes into that folder; at the top level it goes
 * to the top level.
 */
export const useTextFoldersStore = defineStore("textFolders", () => {
  const folders = ref<TextFolder[]>([]);
  /** Folder last opened in the Texts view; null = top level. */
  const currentFolderId = ref<number | null>(null);

  async function load(): Promise<TextFolder[]> {
    folders.value = await api.listFolders();
    if (
      currentFolderId.value !== null &&
      !folders.value.some((f) => f.id === currentFolderId.value)
    ) {
      currentFolderId.value = null;
    }
    return folders.value;
  }

  function reset() {
    folders.value = [];
    currentFolderId.value = null;
  }

  return { folders, currentFolderId, load, reset };
});

import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import { useTextFoldersStore } from "./text-folders";
import { resetUserScopedStores } from "./user-scope";

describe("resetUserScopedStores", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("drops the previous account's folders, but not on a session expiry", () => {
    const folders = useTextFoldersStore();
    folders.folders = [{ id: 7, name: "Mine" } as never];
    folders.currentFolderId = 7;
    resetUserScopedStores({ keepReading: true });
    expect(folders.currentFolderId).toBe(7);
    resetUserScopedStores();
    expect(folders.folders).toEqual([]);
    expect(folders.currentFolderId).toBeNull();
  });
});

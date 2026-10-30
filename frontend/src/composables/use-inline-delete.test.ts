import { describe, expect, it, vi } from "vitest";

import { useInlineDelete } from "@/composables/use-inline-delete";

describe("useInlineDelete", () => {
  it("marks the row while it is deleted and disarms it after", async () => {
    let finish!: () => void;
    const remove = vi.fn(() => new Promise<void>((r) => (finish = r)));
    const d = useInlineDelete(remove);
    d.pendingId.value = 3;
    const done = d.confirmDelete({ id: 3 });
    expect(d.deletingId.value).toBe(3);
    expect(remove).toHaveBeenCalledWith({ id: 3 });
    finish();
    await done;
    expect(d.deletingId.value).toBeNull();
    expect(d.pendingId.value).toBeNull();
  });

  it("ignores a second confirm while one delete runs", async () => {
    let finish!: () => void;
    const remove = vi.fn(() => new Promise<void>((r) => (finish = r)));
    const d = useInlineDelete(remove);
    const first = d.confirmDelete({ id: 1 });
    await d.confirmDelete({ id: 2 });
    expect(remove).toHaveBeenCalledTimes(1);
    finish();
    await first;
  });

  it("disarms the row when the delete fails", async () => {
    const d = useInlineDelete(() => Promise.reject(new Error("boom")));
    d.pendingId.value = 1;
    await expect(d.confirmDelete({ id: 1 })).rejects.toThrow("boom");
    expect(d.deletingId.value).toBeNull();
    expect(d.pendingId.value).toBeNull();
  });
});

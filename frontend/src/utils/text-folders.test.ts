import { describe, expect, it } from "vitest";

import type { SavedTextSummary, TextFolder } from "@/api/types";

import {
  childFolders,
  folderAndBelow,
  folderCounts,
  folderLabel,
  folderPath,
  textsIn,
} from "./text-folders";

const folders: TextFolder[] = [
  { id: 1, name: "TaiJiMen", parent_id: null, position: null },
  { id: 2, name: "道德经", parent_id: 1, position: 0 },
  { id: 3, name: "金刚经", parent_id: 1, position: 1 },
  { id: 4, name: "Lehrbuch", parent_id: null, position: null },
];

function text(id: number, folder_id: number | null, extra: Partial<SavedTextSummary> = {}) {
  return {
    id,
    title: `t${id}`,
    preview: "",
    date: `2026-10-0${id}T00:00:00Z`,
    tags: null,
    reading_progress: 0,
    known_unique: 0,
    total_unique: 0,
    comprehension_score: null,
    share_token: null,
    glossary_list_ids: null,
    folder_id,
    position: null,
    ...extra,
  } as SavedTextSummary;
}

describe("text folders", () => {
  it("lists subfolders in order, then by name", () => {
    expect(childFolders(folders, null).map((f) => f.name)).toEqual(["Lehrbuch", "TaiJiMen"]);
    expect(childFolders(folders, 1).map((f) => f.id)).toEqual([2, 3]);
  });

  it("walks a folder's path", () => {
    expect(folderPath(folders, 2).map((f) => f.id)).toEqual([1, 2]);
    expect(folderPath(folders, null)).toEqual([]);
    expect(folderLabel(folders, 2)).toBe("TaiJiMen › 道德经");
  });

  it("collects a folder and everything below", () => {
    expect([...folderAndBelow(folders, 1)].sort()).toEqual([1, 2, 3]);
  });

  it("orders a folder by position, the top level by date as given", () => {
    const texts = [
      text(1, 2, { position: 1 }),
      text(2, 2, { position: 0 }),
      text(3, 2),
      text(4, null),
      text(5, null),
    ];
    expect(textsIn(texts, 2).map((t) => t.id)).toEqual([2, 1, 3]);
    expect(textsIn(texts, null).map((t) => t.id)).toEqual([4, 5]);
  });

  it("counts readable texts below a folder", () => {
    const texts = [text(1, 2, { unlocked: true }), text(2, 3), text(3, null, { unlocked: true })];
    expect(folderCounts(folders, texts, 1)).toEqual({ total: 2, readable: 1 });
  });
});

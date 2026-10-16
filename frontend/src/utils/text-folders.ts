/**
 * Folder tree helpers for the saved-texts view: what a folder holds, its
 * path, and how much of it is readable.
 */
import type { SavedTextSummary, TextFolder } from "@/api/types";

/** Subfolders of `parentId` (null = top level), in their order, then by name. */
export function childFolders(folders: TextFolder[], parentId: number | null): TextFolder[] {
  return folders
    .filter((f) => (f.parent_id ?? null) === parentId)
    .sort(
      (a, b) =>
        (a.position ?? Infinity) - (b.position ?? Infinity) ||
        a.name.localeCompare(b.name),
    );
}

/** The folder and its parents, top level first. */
export function folderPath(folders: TextFolder[], id: number | null): TextFolder[] {
  const byId = new Map(folders.map((f) => [f.id, f]));
  const out: TextFolder[] = [];
  const seen = new Set<number>();
  let cur = id === null ? undefined : byId.get(id);
  while (cur && !seen.has(cur.id)) {
    out.unshift(cur);
    seen.add(cur.id);
    cur = cur.parent_id === null ? undefined : byId.get(cur.parent_id);
  }
  return out;
}

/** Ids of the folder and every folder below it. */
export function folderAndBelow(folders: TextFolder[], id: number): Set<number> {
  const out = new Set<number>([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const f of folders) {
      if (f.parent_id !== null && out.has(f.parent_id) && !out.has(f.id)) {
        out.add(f.id);
        grew = true;
      }
    }
  }
  return out;
}

/** Texts directly in a folder, in reading order. The top level lists the
 *  newest first, a folder its own order (then oldest first). */
export function textsIn(
  texts: SavedTextSummary[],
  folderId: number | null,
): SavedTextSummary[] {
  const here = texts.filter((t) => (t.folder_id ?? null) === folderId);
  if (folderId === null) return here;
  return [...here].sort(
    (a, b) =>
      (a.position ?? Infinity) - (b.position ?? Infinity) ||
      a.date.localeCompare(b.date) ||
      a.id - b.id,
  );
}

/** How many texts a folder holds (with its subfolders) and how many of
 *  them are readable. */
export function folderCounts(
  folders: TextFolder[],
  texts: SavedTextSummary[],
  id: number,
): { total: number; readable: number } {
  const ids = folderAndBelow(folders, id);
  const inside = texts.filter((t) => t.folder_id != null && ids.has(t.folder_id));
  return { total: inside.length, readable: inside.filter((t) => t.unlocked).length };
}

/** "TaiJiMen › 道德经" for a folder id, "" at top level. */
export function folderLabel(folders: TextFolder[], id: number | null | undefined): string {
  return folderPath(folders, id ?? null)
    .map((f) => f.name)
    .join(" › ");
}

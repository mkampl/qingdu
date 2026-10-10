/**
 * Other readings of a polyphone (长 cháng "long" · zhǎng "to grow;
 * chief"). The API sends `readings` (main reading first, `is_main` set)
 * for words with more than one dictionary reading; the main one is what
 * the headline/meanings already show, so the UI lists only the rest.
 */
import type { WordReading } from "@/api/types";
import { otherMeanings } from "./meanings";

export interface OtherReading {
  pinyin: string;
  primary: string;
  tags: string[];
  /** Further senses of this reading, without the primary's own. */
  senses: string[];
  example: WordReading["example"];
}

/**
 * Every reading except the main one, in API order, each with its primary
 * gloss plus up to `maxSenses` other senses. A reading whose pinyin
 * repeats the main pinyin (shouldn't happen) is skipped.
 */
export function otherReadings(
  readings: readonly WordReading[] | null | undefined,
  maxSenses = 3,
): OtherReading[] {
  if (!readings || readings.length < 2) return [];
  const main = readings.find((r) => r.is_main) ?? readings[0];
  const out: OtherReading[] = [];
  for (const r of readings) {
    if (r === main || !r.pinyin || r.pinyin === main.pinyin) continue;
    out.push({
      pinyin: r.pinyin,
      primary: r.primary,
      tags: r.meaning_tags ?? [],
      senses: otherMeanings(r.primary, r.meanings, maxSenses),
      example: r.example ?? null,
    });
  }
  return out;
}

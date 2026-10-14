/**
 * Compare a typed pinyin answer with the card's pinyin, tones included.
 *
 * Both sides are reduced to their letters (tone marks, digits, spaces and
 * apostrophes dropped, ü/v/u: folded to u) plus the list of non-neutral
 * tones in order. Tones can be typed as marks (mǎ) or numbers (ma3, lv4);
 * neutral tones can be left out or typed as 5/0. 一 and 不 change tone in
 * speech, so either their citation tone or a sandhi tone counts.
 */

export type PinyinVerdict = "exact" | "toneless" | "wrong-tone" | "wrong";

const MARKS: Record<string, [string, number]> = {
  ā: ["a", 1], á: ["a", 2], ǎ: ["a", 3], à: ["a", 4],
  ē: ["e", 1], é: ["e", 2], ě: ["e", 3], è: ["e", 4],
  ī: ["i", 1], í: ["i", 2], ǐ: ["i", 3], ì: ["i", 4],
  ō: ["o", 1], ó: ["o", 2], ǒ: ["o", 3], ò: ["o", 4],
  ū: ["u", 1], ú: ["u", 2], ǔ: ["u", 3], ù: ["u", 4],
  ǖ: ["u", 1], ǘ: ["u", 2], ǚ: ["u", 3], ǜ: ["u", 4],
};

// Tones 一 and 不 take in connected speech besides their citation tone.
const SANDHI: Record<string, number[]> = { yi: [1, 2, 4], bu: [2, 4] };

interface Parsed {
  letters: string;
  tones: number[];
  /** For the card side: the syllable each tone belongs to. */
  syllables: string[];
}

function parse(input: string): Parsed {
  const text = input.normalize("NFC").toLowerCase().replace(/u:/g, "u");
  let letters = "";
  const tones: number[] = [];
  const syllables: string[] = [];
  for (const chunk of text.split(/[\s'’·-]+/)) {
    let syllable = "";
    for (const ch of chunk) {
      const mark = MARKS[ch];
      if (mark) {
        syllable += mark[0];
        tones.push(mark[1]);
        syllables.push(chunk);
      } else if (ch >= "1" && ch <= "4") {
        tones.push(Number(ch));
        syllables.push(syllable);
        letters += syllable;
        syllable = "";
      } else if (ch === "5" || ch === "0") {
        letters += syllable;
        syllable = "";
      } else if (ch === "ü" || ch === "v") {
        syllable += "u";
      } else if (ch >= "a" && ch <= "z") {
        syllable += ch;
      }
    }
    letters += syllable;
  }
  return { letters, tones, syllables: syllables.map(plain) };
}

function plain(syllable: string): string {
  let out = "";
  for (const ch of syllable) out += MARKS[ch]?.[0] ?? (ch === "ü" || ch === "v" ? "u" : ch);
  return out.replace(/[^a-z]/g, "");
}

export function checkPinyin(guess: string, cardPinyin: string): PinyinVerdict {
  const g = parse(guess);
  const t = parse(cardPinyin);
  if (!g.letters || g.letters !== t.letters) return "wrong";
  if (g.tones.length === 0) return t.tones.length === 0 ? "exact" : "toneless";
  if (g.tones.length !== t.tones.length) return "wrong-tone";
  const ok = t.tones.every((tone, i) => {
    if (g.tones[i] === tone) return true;
    return SANDHI[t.syllables[i]]?.includes(g.tones[i]) ?? false;
  });
  return ok ? "exact" : "wrong-tone";
}

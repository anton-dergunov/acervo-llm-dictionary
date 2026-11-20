/**
 * A Mandarin reading as the Pinyin letters a learner sees, each with the IPA it stands for.
 *
 * `initialAndFinal` is the twin of the server's `mandarin_ipa._initial_and_final`, pinned by the
 * shared vectors (`testFixtures/pinyinPartsVectors.json`, read by both test suites), so the guide
 * cuts a syllable exactly where the stored transcription was made from. The table writes a final as
 * Pinyin spells it after an initial (`iu`, `ui`, `un`), so the full spellings the server reaches map
 * back to those rows, and a bare `i` after zh, ch, sh, r or z, c, s is one of the two apical rows.
 */

import { pinyinSyllables, tonelessSyllable, type Syllable } from "../pinyin";
import { TABLE, type PinyinRow, type PinyinTone } from "./table";

const INITIALS = new Set(["b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "j", "q", "x",
  "zh", "ch", "sh", "r", "z", "c", "s"]);

/** `zhuang` → [`zh`, `uang`], with every spelling rule undone: `you` → [``, `iou`]. */
export function initialAndFinal(bare: string): [string, string] {
  let initial = ["zh", "ch", "sh"].find((candidate) => bare.startsWith(candidate)) ?? "";
  if (!initial && INITIALS.has(bare[0])) initial = bare[0];
  let final = bare.slice(initial.length);
  if (!initial && bare[0] === "y") {
    const rest = bare.slice(1);
    if (rest.startsWith("u")) final = "ü" + rest.slice(1);       // yu yue yuan yun
    else if (rest.startsWith("i")) final = rest;                // yi yin ying
    else final = "i" + rest;                                    // ya ye yao you yan yang yong
  } else if (!initial && bare[0] === "w") {
    const rest = bare.slice(1);
    final = rest.startsWith("u") ? rest : "u" + rest;
  }
  if (["j", "q", "x"].includes(initial) && final.startsWith("u")) final = "ü" + final.slice(1);
  if (["b", "p", "m", "f"].includes(initial) && final === "o") final = "uo";
  // Written short after an initial; `you`, `wei`, `wen` already reached the full spelling above.
  final = ({ iu: "iou", ui: "uei", un: "uen" } as Record<string, string>)[final] ?? final;
  return [initial, final];
}

const SPELT: Record<string, string> = { iou: "iu", uei: "ui", uen: "un" };
const initialRows = new Map(TABLE.pinyin.initials.map((row) => [row.letters, row]));
const finalRows = new Map(TABLE.pinyin.finals.map((row) => [row.letters, row]));
const toneRows = new Map(TABLE.pinyin.tones.map((row) => [row.number, row]));

export function finalRow(initial: string, final: string): PinyinRow | null {
  if (final === "i" && ["zh", "ch", "sh", "r"].includes(initial)) return finalRows.get("-i (zh ch sh r)") ?? null;
  if (final === "i" && ["z", "c", "s"].includes(initial)) return finalRows.get("-i (z c s)") ?? null;
  return finalRows.get(SPELT[final] ?? final) ?? null;
}

/** One syllable as its parts, each a row of the table; a part the syllable lacks is `null`. */
export interface PinyinParts {
  syllable: Syllable;
  initial: PinyinRow | null;
  final: PinyinRow | null;
  erhua: PinyinRow | null;
  tone: PinyinTone | null;
}

/** A reading's syllables as their parts, or `null` when it does not read as Pinyin. */
export function pinyinParts(reading: string): PinyinParts[] | null {
  const syllables = pinyinSyllables(reading);
  if (!syllables) return null;
  return syllables.map((syllable) => {
    const [initial, final] = initialAndFinal(tonelessSyllable(syllable));
    return {
      syllable,
      initial: initial ? initialRows.get(initial) ?? null : null,
      final: finalRow(initial, final),
      erhua: syllable.erhua ? finalRows.get("r (erhua)") ?? null : null,
      tone: toneRows.get(syllable.tone) ?? null
    };
  });
}

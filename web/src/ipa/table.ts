/**
 * The IPA guide's table: what each symbol is, in plain English, and the recording it plays.
 *
 * `symbols.json` is written by hand once and never generated per word; its rows were checked
 * against Wikipedia and its recordings chosen by ear (`experiments/ipa-sounds/`). It is JSON because
 * `yaml.ts` is the only place the app reads YAML. This module only indexes it: which row a symbol
 * typed any of its ways is, and what a run of tone letters says.
 */

import data from "./symbols.json";

/** A letter: a consonant, affricate, vowel, or a letter with a mark recorded as one sound (`tʰ`). */
export interface LetterRow {
  symbol: string;
  name: string;
  how: string;
  like?: string | null;
  heard?: string | null;
  aliases?: string[];
  sound?: string;
}

/** A diacritic, a tone mark, or stress, length and phrasing: a mark with no sound of its own. */
export interface MarkRow {
  symbol: string;
  name: string;
  how?: string;
  example?: string;
  aliases?: string[];
  sound?: string;
}

export interface ToneLetter { symbol: string; level: number; name: string }
export interface Contour { letters: string; name: string; how: string; mandarin?: string; sound?: string }
export interface PinyinRow { letters: string; ipa: string; how: string; example: string; sound?: string }
export interface PinyinTone { mark: string; number: number; ipa: string; how: string; sound?: string }

/** What a CC BY or BY-SA licence asks a changed copy to say. */
export interface Credit {
  source: string;
  author: string;
  licence: string;
  licenceUrl: string | null;
  page: string;
  changes: string;
}

interface Table {
  consonants: LetterRow[];
  affricates: LetterRow[];
  combinations: LetterRow[];
  vowels: LetterRow[];
  diacritics: MarkRow[];
  suprasegmentals: MarkRow[];
  tones: { letters: ToneLetter[]; contours: Contour[]; marks: MarkRow[] };
  pinyin: { initials: PinyinRow[]; finals: PinyinRow[]; tones: PinyinTone[] };
  recordings: Record<string, Credit>;
}

export const TABLE = data as unknown as Table;

const written = (row: { symbol: string; aliases?: string[] }): string[] => [row.symbol, ...(row.aliases ?? [])];

/** Every way a letter is typed → its row. Combinations and tie-barred affricates are several characters. */
export const LETTERS = new Map<string, LetterRow>();
for (const row of [...TABLE.consonants, ...TABLE.affricates, ...TABLE.vowels, ...TABLE.combinations]) {
  for (const form of written(row)) LETTERS.set(form.normalize("NFC"), row);
}
/** The longest letter, in characters: how far ahead the splitter looks. */
export const LONGEST_LETTER = Math.max(...Array.from(LETTERS.keys(), (form) => Array.from(form).length));

/** Marks that belong to the letter before them: diacritics, tone marks over a vowel, and length. */
export const LETTER_MARKS = new Map<string, MarkRow>();
for (const row of [...TABLE.diacritics, ...TABLE.tones.marks]) for (const form of written(row)) LETTER_MARKS.set(form, row);
for (const row of TABLE.suprasegmentals) {
  if (["ː", "ˑ", "̆"].includes(row.symbol)) for (const form of written(row)) LETTER_MARKS.set(form, row);
}

/** Marks that stand between sounds: stress and phrasing. The syllable break `.` is not one. */
export const STANDING_MARKS = new Map<string, MarkRow>();
for (const row of TABLE.suprasegmentals) {
  if (!LETTER_MARKS.has(row.symbol) && row.symbol !== ".") for (const form of written(row)) STANDING_MARKS.set(form, row);
}

export const TONE_LETTERS = new Map(TABLE.tones.letters.map((letter) => [letter.symbol, letter]));

export const TIE_BARS = new Set(written(TABLE.diacritics.find((row) => row.name === "tie bar")!));

export const STRESS = new Set(["ˈ", "ˌ"]);

/** What a run of tone letters says: a contour the table names, or one described from its levels. */
export interface ToneReading {
  name: string;
  how: string;
  mandarin?: string;
  sound?: string;
  levels: number[];
}

const LEVEL_NAME = new Map(TABLE.tones.letters.map((letter) => [letter.level, letter.name]));

export function readTone(letters: string): ToneReading {
  const levels = Array.from(letters, (letter) => TONE_LETTERS.get(letter)?.level ?? 3);
  const named = TABLE.tones.contours.find((contour) => contour.letters === letters);
  if (named) return { ...named, levels };
  const steps = levels.filter((level, index) => index === 0 || level !== levels[index - 1]);
  if (steps.length === 1) return { name: `${LEVEL_NAME.get(steps[0])} level`, how: "The pitch stays at one height.", levels };
  const path = steps.map((level) => LEVEL_NAME.get(level)).join(", then ");
  return { name: steps.length === 2 ? (steps[1] > steps[0] ? "rising" : "falling") : "contour", how: `The pitch moves from ${path}.`, levels };
}

/**
 * What a recording says when it is a word rather than the sound on its own: a Mandarin syllable
 * (`Zh-dà.ogg`, which every Pinyin row plays) or an English word (`En-us-er.ogg`). `null` for a
 * recording of the sound itself.
 */
export function recordingSays(sound: string | undefined): string | null {
  const source = sound ? TABLE.recordings[sound]?.source : undefined;
  const found = source?.match(/^(?:Zh|En-us)-(.+)\.og[ga]$/);
  return found ? found[1].normalize("NFC") : null;
}

/** The recording a file name stands for, and the credit it carries. */
export function creditOf(sound: string): Credit | null {
  return TABLE.recordings[sound] ?? null;
}

/**
 * A transcription cut into the sounds a learner looks up, in the order it has them.
 *
 * IPA is one alphabet, so this is told no language. A letter keeps the marks written on or after it
 * (`u̯`, `aː`, `kʷ`), so a diacritic is explained inside its letter; a letter with a mark that has a
 * recording of its own (`tʰ`, `ɑ̃`) is matched whole, longest first, before its bare letter. An
 * affricate is one sound with or without its tie bar (`ts`, `t͡s`), and two other letters joined by a
 * tie bar are one sound of two parts. A run of tone letters is one tone. Stress and phrasing marks
 * stand between sounds; slashes, brackets, spaces and the syllable break are not sounds. A character
 * the table does not know is kept as an unknown unit, never dropped.
 */

import {
  LETTERS, LETTER_MARKS, LONGEST_LETTER, STANDING_MARKS, TIE_BARS, TONE_LETTERS,
  type LetterRow, type MarkRow
} from "./table";

export interface MarkUse { text: string; row: MarkRow }

export type Unit =
  /** `rows` is one letter, or two joined by a tie bar; `marks` are those written on it. */
  | { kind: "sound"; text: string; rows: LetterRow[]; marks: MarkUse[] }
  | { kind: "tone"; text: string }
  | { kind: "mark"; text: string; row: MarkRow }
  | { kind: "unknown"; text: string };

const SKIPPED = new Set(["/", "[", "]", "(", ")", " ", " ", ".", "-"]);

function letterAt(characters: string[], at: number): { row: LetterRow; length: number } | null {
  for (let length = Math.min(LONGEST_LETTER, characters.length - at); length > 0; length -= 1) {
    const row = LETTERS.get(characters.slice(at, at + length).join("").normalize("NFC"));
    if (row) return { row, length };
  }
  return null;
}

/** Precomposed letters the table does not hold (`é`, `ã`) read as their letter and its marks. */
function decomposed(text: string): string[] {
  return Array.from(text).flatMap((character) =>
    LETTERS.has(character) || STANDING_MARKS.has(character) || TONE_LETTERS.has(character)
      ? [character]
      : Array.from(character.normalize("NFD")));
}

export function splitTranscription(transcription: string): Unit[] {
  const characters = decomposed(transcription.normalize("NFC"));
  const units: Unit[] = [];
  let at = 0;
  while (at < characters.length) {
    const character = characters[at];
    if (SKIPPED.has(character)) { at += 1; continue; }
    if (TONE_LETTERS.has(character)) {
      let end = at;
      while (end < characters.length && TONE_LETTERS.has(characters[end])) end += 1;
      units.push({ kind: "tone", text: characters.slice(at, end).join("") });
      at = end;
      continue;
    }
    const standing = STANDING_MARKS.get(character);
    if (standing) { units.push({ kind: "mark", text: character, row: standing }); at += 1; continue; }
    const letter = letterAt(characters, at);
    if (!letter) {
      const mark = LETTER_MARKS.get(character);
      const last = units[units.length - 1];
      if (mark && last?.kind === "sound") {
        last.marks.push({ text: character, row: mark });
        last.text += character;
      } else units.push({ kind: "unknown", text: character });
      at += 1;
      continue;
    }
    const unit: Extract<Unit, { kind: "sound" }> = {
      kind: "sound", text: characters.slice(at, at + letter.length).join(""), rows: [letter.row], marks: []
    };
    at += letter.length;
    for (;;) {
      const next = characters[at];
      if (next !== undefined && TIE_BARS.has(next)) {
        const joined = letterAt(characters, at + 1);
        if (joined) {
          unit.rows.push(joined.row);
          unit.marks.push({ text: next, row: LETTER_MARKS.get(next)! });
          unit.text += next + characters.slice(at + 1, at + 1 + joined.length).join("");
          at += 1 + joined.length;
          continue;
        }
      }
      const mark = next === undefined ? undefined : LETTER_MARKS.get(next);
      if (!mark) break;
      unit.marks.push({ text: next, row: mark });
      unit.text += next;
      at += 1;
    }
    units.push(unit);
  }
  return units;
}

/** The units a panel lists: each sound, tone and mark once, at its first place. */
export function distinctUnits(units: Unit[]): Unit[] {
  const seen = new Set<string>();
  return units.filter((unit) => {
    const key = `${unit.kind}:${unit.text.normalize("NFC")}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** The recording a sound plays: its own when it is a combination, its letter's when it is marked. */
export function soundOf(unit: Unit): string | undefined {
  return unit.kind === "sound" && unit.rows.length === 1 ? unit.rows[0].sound : undefined;
}

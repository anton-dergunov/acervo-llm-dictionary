/**
 * A word's reading as a learner reads it: for Mandarin, tones shown as tones.
 *
 * A Mandarin reading is drawn from its syllables, never from the stored string, so numbered and
 * tone-marked Pinyin look the same (`docs/features/articles.md`, "Readings"). Each syllable carries a
 * `tone-1`…`tone-5` class, which is its colour; on the word page each character also stands over its
 * own syllable, with the pitch contour of its tone above it. Any other reading is shown as written.
 */

import { Fragment } from "react";
import type { Lexeme } from "./domain";
import { isMandarin } from "./languages";
import { alignHanzi, pinyinSyllables, type HanziColumn } from "./pinyin";

type Readable = Pick<Lexeme, "language" | "headword" | "reading">;

/** The headword's characters paired with their syllables, or `null` where they do not pair. */
export function hanziColumns(lexeme: Readable): HanziColumn[] | null {
  if (!lexeme.reading || !isMandarin(lexeme.language)) return null;
  const syllables = pinyinSyllables(lexeme.reading);
  return syllables ? alignHanzi(lexeme.headword, syllables) : null;
}

/**
 * The characters of a Mandarin headword, each a column over its syllable. It goes *inside* the
 * headword's own element, which keeps its `data-say`: the syllable and the contour are drawn by CSS
 * from `data-reading` and the tone class, so the element's text stays exactly the headword — what a
 * selection reads aloud, and what can be copied.
 */
export function HanziColumns({ columns }: { columns: readonly HanziColumn[] }) {
  let lastFull: number | null = null;
  return <>{columns.map((column, index) => {
    const { tone } = column.syllable;
    // A neutral syllable has no pitch of its own: it lands where the full tone before it leaves the
    // voice, so its dot is drawn at that height (`after-1`…`after-4`). A run of neutral syllables
    // stays at the height of the first; one with no full tone before it sits in the middle.
    const after = tone === 5 && lastFull ? ` after-${lastFull}` : "";
    if (tone !== 5) lastFull = tone;
    return <span key={index} className={`hz tone-${tone}${after}`} data-reading={column.syllable.text}>
      {column.characters}
    </span>;
  })}</>;
}

/** A reading on one line: Mandarin syllables tone-marked and coloured by tone, anything else as written. */
export function ReadingText({ reading, language }: { reading: string; language: string }) {
  const syllables = isMandarin(language) ? pinyinSyllables(reading) : null;
  if (!syllables) return <>{reading}</>;
  return <>{syllables.map((syllable, index) => <Fragment key={index}>
    {syllable.before}<span className={`tone-${syllable.tone}`}>{syllable.text}</span>
  </Fragment>)}</>;
}

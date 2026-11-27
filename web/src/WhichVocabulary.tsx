/**
 * "Which vocabulary?" — asked when a word could go in several of the owner's vocabularies
 * (`docs/features/capture.md`, "Which vocabulary").
 *
 * A word goes in the vocabulary in view when it is in its language, and otherwise in the only
 * vocabulary of its language. Only when there are several of that language and none of them is in
 * view is there a question, and it is the owner's: two vocabularies of one language are told apart by
 * nothing but their names, so no rule could guess which one a word belongs in. The question is the
 * same wherever a word is added — a capture, a photo, a word tapped while reading, a typed document —
 * and the answer is sent again as the vocabulary asked for.
 */

import { useId } from "react";
import { AcervoApiError } from "./api";
import type { Vocabulary, VocabularyGraph } from "./domain";
import { languageName, presentationOf } from "./languages";
import { vocabularies } from "./selectors";

export interface VocabularyQuestion {
  language: string;
  choices: Vocabulary[];
}

/**
 * The question a refusal asks, when it is the server's `vocabulary_ambiguous`: the vocabularies it
 * names, as this replica holds them. Null for any other failure, and for one naming vocabularies the
 * replica has not pulled yet — its sentence names them, and is shown instead.
 */
export function vocabularyQuestion(error: unknown, graph: VocabularyGraph | null): VocabularyQuestion | null {
  if (!(error instanceof AcervoApiError) || error.code !== "vocabulary_ambiguous" || !graph) return null;
  const { language, vocabularies: named } = error.asking;
  if (typeof language !== "string" || !Array.isArray(named)) return null;
  const held = vocabularies(graph);
  const choices = named.flatMap((id) => held.filter((entry) => entry.id === id));
  return choices.length === named.length && choices.length > 1 ? { language, choices } : null;
}

export function WhichVocabulary({ question, typed = false, onChoose }: {
  question: VocabularyQuestion;
  /** A document the owner wrote says its language; a capture's was worked out from the text. */
  typed?: boolean;
  onChoose(vocabularyId: string): void;
}) {
  const title = useId();
  const name = languageName(question.language);
  return <div className="which-vocab" role="group" aria-labelledby={title}>
    <p id={title}>
      {typed ? `This word is in ${name}.` : `This looks like ${name}.`} Which of your {name} vocabularies
      does it go in?
    </p>
    <div className="which-list">
      {question.choices.map((choice) => {
        const shown = presentationOf(choice);
        return <button key={choice.id} type="button" className="tb-btn" onClick={() => onChoose(choice.id)}>
          <span aria-hidden="true">{shown.flag}</span><span>{shown.name}</span>
        </button>;
      })}
    </div>
  </div>;
}

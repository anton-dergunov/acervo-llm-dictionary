/* What `POST /articles` does to a document, for the fakes that stand in for the server in tests.

   The real diff is `src/acervo/services/articles.py`, and `tests/unit/server/test_articles.py` is
   its suite. This is the same rules written small enough that a fake server can answer a save the
   way the real one would — ids kept, children claimed, removed records tombstoned — so the
   interface's tests can go on asserting what a saved article looks like on the device. It is used
   by nothing that ships. */

import type {
  Attestation, EntityKind, Example, ImagePrompt, Lexeme, Sense, VocabularyGraph
} from "./domain";
import type { Entity } from "./repository";
import { clipExampleId, imagePromptId, newId } from "./ids";
import type { ArticleDraft, ImagePromptDraft } from "./yaml";

export interface ArticleChanges {
  lexemeId: string;
  changes: Partial<VocabularyGraph>;
}

export function articleChanges(
  graph: VocabularyGraph,
  draft: ArticleDraft,
  minted: ReadonlySet<string>,
  who: { ownerId: string; deviceId: string },
  at = new Date().toISOString(),
  /** Where a new word goes, as the save names it; a stored word stays in its own, as on the server. */
  vocabularyId?: string
): ArticleChanges {
  const changed: Partial<VocabularyGraph> = {};
  const change = <T extends Entity>(store: EntityKind, value: T) => {
    const list = (changed[store] ?? []) as T[];
    list.push(value);
    changed[store] = list as never;
  };
  const live = <T extends Entity>(records: T[]): T[] => records.filter((record) => !record.deleted);
  const find = <T extends Entity>(records: T[], id: string | null): T | undefined =>
    id ? records.find((record) => record.id === id) : undefined;
  const stamp = (existing?: Entity) => ({
    ownerId: who.ownerId, deleted: false, createdAt: existing?.createdAt ?? at, editedAt: at,
    editedBy: who.deviceId, revision: existing?.revision ?? 0
  });

  const lexemeId = draft.id ?? newId();
  const existingLexeme = find(graph.lexemes, draft.id);
  if (draft.id && (!existingLexeme || existingLexeme.deleted)) {
    throw new Error("This document names an entry that is not in your vocabulary, so it was not saved.");
  }
  const into = existingLexeme?.vocabularyId ?? vocabularyId;
  if (!into) throw new Error("Say which vocabulary this entry goes in.");
  const topicIds = draft.topics.map((name) => {
    const topic = live(graph.topics).find((one) => one.name.toLowerCase() === name.trim().toLowerCase());
    if (!topic) {
      const known = live(graph.topics).map((one) => one.name).sort().join(", ");
      throw new Error(`There is no topic called "${name}". Topics are created deliberately; the ones you have are: ${known || "none yet"}.`);
    }
    return topic.id;
  });
  change("lexemes", {
    ...existingLexeme, id: lexemeId, vocabularyId: into, language: draft.language, headword: draft.headword,
    lemma: draft.lemma, reading: draft.reading, ipa: draft.ipa, pos: draft.pos, gender: draft.gender,
    register: draft.register, dialect: draft.dialect, emoji: draft.emoji, topicIds,
    status: draft.status, shortGloss: draft.shortGloss, primaryGloss: draft.primaryGloss,
    emotion: draft.emotion, notes: draft.notes,
    clipsSearchedAt: existingLexeme?.clipsSearchedAt ?? null, ...stamp(existingLexeme)
  } as Lexeme);

  const minting = draft.id === null;
  const claim = <T extends Entity>(records: T[], id: string | null, owner: (record: T) => boolean): T | undefined => {
    const existing = find(records, id);
    if (!existing) {
      if (id && !minting && !minted.has(id)) throw new Error(`This document names a record that is not in your vocabulary (${id}), so it was not saved.`);
      return undefined;
    }
    if (!owner(existing)) throw new Error(`The id ${id} belongs to a different entry, so this document was not saved.`);
    return existing;
  };

  const kept = { sense: new Set<string>(), example: new Set<string>(), attestation: new Set<string>(), prompt: new Set<string>() };

  const prompt = (image: ImagePromptDraft, senseId: string | null) => {
    let existing = claim(graph.imagePrompts, image.id, (record) => record.lexemeId === lexemeId);
    const id = image.id ?? (senseId ? imagePromptId(senseId) : newId());
    if (!image.id) existing = find(graph.imagePrompts, id);
    kept.prompt.add(id);
    change("imagePrompts", {
      attempts: 0, failureReason: null, suppressed: false, ...existing, id, lexemeId, senseId,
      exampleId: image.exampleId, prompt: image.prompt, styleId: image.styleId, seed: image.seed,
      modelId: image.modelId, promptVersion: image.promptVersion, imageRef: image.imageRef,
      imageModelId: image.imageModelId, ...stamp(existing)
    } as ImagePrompt);
  };

  draft.attestations.forEach((attestation) => {
    const existing = claim(graph.attestations, attestation.id, (record) => record.lexemeId === lexemeId);
    const id = attestation.id ?? newId();
    kept.attestation.add(id);
    change("attestations", {
      ...existing, id, lexemeId, text: attestation.text, translation: attestation.translation,
      sourceUrl: attestation.sourceUrl, sourceTitle: attestation.sourceTitle,
      sourceKind: attestation.sourceKind,
      capturedAt: attestation.capturedAt.trim() || existing?.capturedAt || at,
      photoRef: attestation.photoRef, photoRegion: attestation.photoRegion, ...stamp(existing)
    } as Attestation);
  });

  draft.senses.forEach((sense) => {
    const existing = claim(graph.senses, sense.id, (record) => record.lexemeId === lexemeId);
    const senseId = sense.id ?? newId();
    kept.sense.add(senseId);
    change("senses", {
      ...existing, id: senseId, lexemeId, definition: sense.definition,
      definitionLang: sense.definitionLang, glosses: sense.glosses, domain: sense.domain,
      emoji: sense.emoji, order: sense.order, ...stamp(existing)
    } as Sense);
    sense.examples.forEach((example) => {
      let current = claim(graph.examples, example.id, (record) =>
        graph.senses.some((one) => one.id === record.senseId && one.lexemeId === lexemeId));
      const id = example.id ?? (example.clipRef ? clipExampleId(senseId, example.clipRef) : newId());
      if (!example.id) current = find(graph.examples, id);
      kept.example.add(id);
      const { id: _ignored, ...content } = example;
      change("examples", { ...current, ...content, id, senseId, ...stamp(current) } as Example);
    });
    sense.images.forEach((image) => prompt(image, senseId));
  });
  draft.images.forEach((image) => prompt(image, null));

  const tombstone = <T extends Entity>(store: EntityKind, record: T) =>
    change(store, { ...record, ...stamp(record), deleted: true } as T);
  const senseIds = new Set(live(graph.senses).filter((one) => one.lexemeId === lexemeId).map((one) => one.id));
  live(graph.senses).filter((one) => one.lexemeId === lexemeId && !kept.sense.has(one.id))
    .forEach((one) => tombstone("senses", one));
  live(graph.attestations).filter((one) => one.lexemeId === lexemeId && !kept.attestation.has(one.id))
    .forEach((one) => tombstone("attestations", one));
  live(graph.examples).filter((one) => senseIds.has(one.senseId) && !kept.example.has(one.id))
    .forEach((one) => tombstone("examples", one));
  live(graph.imagePrompts).filter((one) => one.lexemeId === lexemeId && !kept.prompt.has(one.id))
    .forEach((one) => tombstone("imagePrompts", one));
  const targets: Record<string, Set<string>> = { sense: kept.sense, example: kept.example, attestation: kept.attestation };
  live(graph.pronunciations)
    .filter((one) => one.lexemeId === lexemeId && one.targetKind !== "lexeme" && !targets[one.targetKind].has(one.targetId))
    .forEach((one) => tombstone("pronunciations", one));

  return { lexemeId, changes: changed };
}

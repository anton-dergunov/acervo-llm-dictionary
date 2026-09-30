/* What a proposal is allowed to do to an article, and what it must be refused for.
 *
 * `articleEdit.ts` is the only place the edit language is understood, and it is the one thing
 * standing between a model's answer and the owner's entry. Everything here is a contract test. */

import { describe, expect, it } from "vitest";
import {
  applyOps, diffDrafts, EditRefused, SETTABLE, type EditOp, type FoldedPhoto
} from "./articleEdit";
import { articleFor, articleFromDraft } from "./selectors";
import { testGraph } from "./testGraph";
import {
  ARTICLE_KEYS, ATTESTATION_KEYS, draftFor, EXAMPLE_KEYS, parseArticle, SENSE_KEYS, yamlForDraft
} from "./yaml";

const PICAR = "lexemepicar0001";
const ITCH = "sensepicaritch0";
const CHOP = "sensepicarchop0";
const ITCH_EXAMPLE = "examplepicar010";
const ATTESTATION = "attestpicar0010";

const graph = testGraph();
const draft = () => draftFor(articleFor(graph, PICAR)!);

let minted = 0;
const context = {
  modelId: "gemini-3.1-flash-lite",
  glossLang: "en",
  // Deterministic, and a real 15-character lowercase alphanumeric id so the round-trip test is
  // asserting against what `newId` actually produces rather than a shape of its own.
  mintId: () => `mint${String(++minted).padStart(11, "0")}`
};

const apply = (ops: EditOp[]) => applyOps(draft(), ops, context);

describe("what may be set", () => {
  it("refuses a field that is not in the table for that kind of record", () => {
    expect(() => apply([{ op: "set", target: "lexeme", field: "language", value: "fr" }]))
      .toThrow(/not something chat can change/);
    expect(() => apply([{ op: "set", target: "lexeme", field: "id", value: "aaaaaaaaaaaaaaa" }]))
      .toThrow(EditRefused);
    expect(() => apply([{ op: "set", target: `sense:${ITCH}`, field: "order", value: 3 }]))
      .toThrow(EditRefused);
    // Provenance is modelled, never flagged, and never set by the model.
    expect(() => apply([{ op: "set", target: `example:${ITCH_EXAMPLE}`, field: "origin", value: "manual" }]))
      .toThrow(EditRefused);
  });

  it("refuses a value of the wrong kind", () => {
    expect(() => apply([{ op: "set", target: "lexeme", field: "notes", value: "one note" }]))
      .toThrow(/wrong kind/);
    expect(() => apply([{ op: "set", target: "lexeme", field: "pos", value: "substantive" }]))
      .toThrow(/wrong kind/);
  });

  it("keeps every settable table a strict subset of the document's own vocabulary", () => {
    // One vocabulary, so a field added to the projection is noticed in one place rather than
    // drifting into a second list nobody remembers to update.
    const subset = (fields: object, keys: string[]) =>
      Object.keys(fields).every((field) => keys.includes(field));
    expect(subset(SETTABLE.lexeme, ARTICLE_KEYS)).toBe(true);
    expect(subset(SETTABLE.sense, SENSE_KEYS)).toBe(true);
    expect(subset(SETTABLE.example, EXAMPLE_KEYS)).toBe(true);
    expect(subset(SETTABLE.attestation, ATTESTATION_KEYS)).toBe(true);
    expect(Object.keys(SETTABLE.lexeme)).not.toContain("id");
    expect(Object.keys(SETTABLE.lexeme)).not.toContain("language");
  });
});

describe("applying", () => {
  it("applies operations in order", () => {
    const { draft: after } = apply([
      { op: "set", target: "lexeme", field: "notes", value: ["first"] },
      { op: "set", target: "lexeme", field: "notes", value: ["second"] }
    ]);
    expect(after.notes).toEqual(["second"]);
  });

  it("refuses the whole set when one id is not in the document, and changes nothing", () => {
    const before = draft();
    expect(() => applyOps(before, [
      { op: "set", target: "lexeme", field: "emoji", value: "🌶" },
      { op: "set", target: "sense:nosuchsense001", field: "domain", value: "cooking" }
    ], context)).toThrow(/not there/);
    // The refusal is structural: the work happens on a clone, so no partial edit is reachable.
    expect(before.emoji).toEqual(draft().emoji);
  });

  it("refuses more than twelve operations", () => {
    const ops: EditOp[] = Array.from({ length: 13 }, () =>
      ({ op: "set", target: "lexeme", field: "emoji", value: "🌶" }) as EditOp);
    expect(() => apply(ops)).toThrow(/rewrite rather than an edit/);
  });

  it("refuses a proposal that touches over half the entry", () => {
    expect(() => apply([
      { op: "set", target: `sense:${ITCH}`, field: "definition", value: "Uno." },
      { op: "set", target: `sense:${CHOP}`, field: "definition", value: "Dos." },
      { op: "set", target: `example:${ITCH_EXAMPLE}`, field: "text", value: "Tres." },
      { op: "set", target: `attestation:${ATTESTATION}`, field: "translation", value: "Cuatro." }
    ])).toThrow(/rewrite rather than an edit/);
  });

  it("allows an ordinary edit that would trip an unconditional half rule", () => {
    // A small entry has few records, so "fix the definition and add an example" is already over
    // half of one. That is an edit, not a rewrite, and the cap must not refuse it.
    const small = draftFor(articleFor(graph, "lexemebalsa0001")!);
    const { draft: after } = applyOps(small, [
      { op: "set", target: "sense:sensebalsaraft0", field: "definition", value: "Embarcación plana y ligera." },
      { op: "add", target: "example", in: "sensebalsaraft0", value: { text: "La balsa flotaba." } }
    ], context);
    expect(after.senses[0].examples).toHaveLength(2);
  });
});

describe("provenance, which the applier derives and the model never sets", () => {
  it("gives an example the model wrote the generated origin and the model id", () => {
    const { draft: after, minted: ids } = apply([
      { op: "add", target: "example", in: ITCH, value: { text: "Me pica la espalda.", translation: "My back itches." } }
    ]);
    const added = after.senses[0].examples.at(-1)!;
    expect(added.origin).toBe("llm");
    expect(added.modelId).toBe("gemini-3.1-flash-lite");
    expect(added.sourceAttestationId).toBeNull();
    /* An added record gets a real id here rather than being left for `saveArticle` to mint on the
       way out. A record with no id has no name in the document the *next* turn is given, so
       "add an example" followed by "make that one more concrete" asked the model to address
       something anonymous — and it invented an id, which is refused. */
    expect(added.id).toMatch(/^[a-z0-9]{15}$/);
    expect([...ids]).toContain(added.id);
    // Reviewing the rendered article *is* the approve gesture, so nothing lands wearing a chip
    // saying it has not been looked at.
  });

  it("resolves a ref, so a sentence you supplied becomes an attestation the example names", () => {
    const { draft: after, minted: ids } = apply([
      {
        op: "add", target: "attestation", ref: "a1",
        value: { text: "Se disfrazó de médico.", translation: "He dressed up as a doctor.", sourceKind: "video" }
      },
      { op: "add", target: "example", in: ITCH, fromAttestation: "a1",
        value: { text: "Se disfrazó de médico.", translation: "He dressed up as a doctor." }
      }
    ]);
    const attestation = after.attestations.at(-1)!;
    const added = after.senses[0].examples.at(-1)!;
    expect(added.origin).toBe("attestation");
    expect(added.sourceAttestationId).toBe(attestation.id);
    expect(added.modelId).toBeNull();
    // Both are minted here, and both are declared, so `saveArticle` reads them as creations.
    expect([...ids].sort()).toEqual([attestation.id, added.id].sort());
  });

  it("refuses an example that quotes a sentence nothing supplied", () => {
    expect(() => apply([
      { op: "add", target: "example", in: ITCH, fromAttestation: "a1", value: { text: "Hola." } }
    ])).toThrow(/quoted a sentence it did not supply/);
  });

  it("folds a new example onto a sentence the entry already holds", () => {
    const { draft: after } = apply([
      { op: "add", target: "example", in: ITCH, fromAttestation: ATTESTATION, value: { text: "Esa salsa pica." } }
    ]);
    expect(after.senses[0].examples.at(-1)!.sourceAttestationId).toBe(ATTESTATION);
  });
});

describe("a photo folded in with the conversation", () => {
  const photo: FoldedPhoto = {
    sentence: "Me pica mucho la picadura del mosquito.",
    photoRef: "photos/owner0000000001/0123456789abcdef.jpg",
    photoRegion: { words: [[[0.1, 0.2], [0.3, 0.2], [0.3, 0.25]]], sentence: [[[0.1, 0.2], [0.9, 0.2], [0.9, 0.3]]] },
    sourceKind: "book"
  };
  const withPhoto = (ops: EditOp[], folded: FoldedPhoto = photo, from = draft()) =>
    applyOps(from, ops, { ...context, photo: folded });
  const addSentence = (text: string, ref = "a1"): EditOp =>
    ({ op: "add", target: "attestation", ref, value: { text } });

  it("goes with the sentence that was photographed, quotes and spacing aside", () => {
    const { draft: after } = withPhoto([
      addSentence("Otra frase."),
      addSentence("«Me pica  mucho la picadura del mosquito.»", "a2")
    ]);
    const [other, photographed] = after.attestations.slice(-2);
    expect(photographed.photoRef).toBe(photo.photoRef);
    expect(photographed.photoRegion).toEqual(photo.photoRegion);
    expect(photographed.sourceKind).toBe("book");
    expect(other.photoRef).toBeNull();
  });

  it("goes with the one sentence added when the model reworded it", () => {
    const { draft: after } = withPhoto([addSentence("Me pica la picadura.")]);
    expect(after.attestations.at(-1)!.photoRef).toBe(photo.photoRef);
  });

  it("is attached to nothing when no sentence is added, or when it cannot tell which", () => {
    const { draft: edited } = withPhoto([
      { op: "set", target: `sense:${ITCH}`, field: "definition", value: "Sentir picor." }
    ]);
    expect(edited.attestations.some((one) => one.photoRef)).toBe(false);
    const { draft: two } = withPhoto([addSentence("Una."), addSentence("Dos.", "a2")]);
    expect(two.attestations.some((one) => one.photoRef)).toBe(false);
  });

  it("keeps a sign as an attestation of its own, proposed with nothing from the model", () => {
    const sign = { ...photo, sentence: null, sourceKind: "sign" as const };
    const { draft: after, minted: ids } = withPhoto([], sign);
    const kept = after.attestations.at(-1)!;
    expect(kept).toMatchObject({ text: "", photoRef: sign.photoRef, sourceKind: "sign" });
    expect([...ids]).toEqual([kept.id]);
    // Readable as a document: a sign is the one attestation with no text.
    expect(parseArticle(yamlForDraft(after)).attestations.at(-1)!.photoRef).toBe(sign.photoRef);
  });

  it("is attached once, however many turns build on the draft", () => {
    const sign = { ...photo, sentence: null };
    const { draft: first } = withPhoto([], sign);
    const { draft: second } = withPhoto([addSentence("Otra frase.")], sign, first);
    expect(second.attestations.filter((one) => one.photoRef === sign.photoRef)).toHaveLength(1);
    expect(() => withPhoto([], sign, first)).toThrow(/changes nothing/);
  });
});

describe("the two agreements the data model imposes", () => {
  it("fills the translation language when an example gains a translation", () => {
    const { draft: after } = apply([
      { op: "set", target: `example:${ITCH_EXAMPLE}`, field: "translation", value: "My nose itches badly." }
    ]);
    const example = after.senses.flatMap((sense) => sense.examples).find((item) => item.id === ITCH_EXAMPLE)!;
    expect(example.translationLang).toBe("en");
  });

  it("clears the translation language when the translation goes", () => {
    const { draft: after } = apply([
      { op: "set", target: `example:${ITCH_EXAMPLE}`, field: "translation", value: null }
    ]);
    const example = after.senses.flatMap((sense) => sense.examples).find((item) => item.id === ITCH_EXAMPLE)!;
    expect(example.translationLang).toBeNull();
  });

  it("drops a marked form that is not in the sentence, and keeps the rest of the edit", () => {
    // The one deliberate exception to all-or-nothing: a model that retypes the dictionary form
    // instead of copying the inflected one should cost the emphasis, not the whole answer.
    const { draft: after } = apply([
      { op: "add", target: "example", in: ITCH, value: { text: "Me pica la espalda.", matchedForm: "picar" } }
    ]);
    const added = after.senses[0].examples.at(-1)!;
    expect(added.text).toBe("Me pica la espalda.");
    expect(added.matchedForm).toBeNull();
  });
});

describe("removing", () => {
  it("refuses to leave the entry with no meanings", () => {
    const small = draftFor(articleFor(graph, "lexemebalsa0001")!);
    expect(() => applyOps(small, [{ op: "remove", target: "sense:sensebalsaraft0", reason: "wrong" }], context))
      .toThrow(/no meanings/);
  });

  it("refuses to remove a sentence an example was drawn from", () => {
    expect(() => apply([{ op: "remove", target: `attestation:${ATTESTATION}`, reason: "tidy" }]))
      .toThrow(/where an example came from/);
  });

  it("removes an example", () => {
    const { draft: after } = apply([{ op: "remove", target: `example:${ITCH_EXAMPLE}`, reason: "duplicate" }]);
    expect(after.senses.flatMap((sense) => sense.examples).some((item) => item.id === ITCH_EXAMPLE)).toBe(false);
  });
});

describe("reordering", () => {
  it("reorders the senses and renumbers them", () => {
    const { draft: after } = apply([{ op: "reorder", target: "senses", ids: [CHOP, ITCH] }]);
    expect(after.senses.map((sense) => sense.id)).toEqual([CHOP, ITCH]);
    expect(after.senses.map((sense) => sense.order)).toEqual([0, 1]);
  });

  it("refuses a list that is not the entry's meanings", () => {
    expect(() => apply([{ op: "reorder", target: "senses", ids: [ITCH] }])).toThrow(EditRefused);
  });
});

describe("the round trip", () => {
  it("survives the projection, which is what the save path actually writes", () => {
    const { draft: after } = apply([
      { op: "set", target: "lexeme", field: "notes", value: ["Not «rascar»."] },
      { op: "add", target: "example", in: ITCH, value: { text: "Me pica la espalda.", translation: "My back itches." } }
    ]);
    const reparsed = parseArticle(yamlForDraft(after));
    expect(reparsed.notes).toEqual(["Not «rascar»."]);
    const added = reparsed.senses[0].examples.at(-1)!;
    expect(added.text).toBe("Me pica la espalda.");
    expect(added.origin).toBe("llm");
  });
});

describe("the diff", () => {
  it("marks added, changed and removed by record id", () => {
    const before = draft();
    const { draft: after } = applyOps(before, [
      { op: "set", target: `sense:${ITCH}`, field: "domain", value: "medicine" },
      { op: "add", target: "example", in: CHOP, value: { text: "Pica el ajo." } },
      { op: "remove", target: `example:${ITCH_EXAMPLE}`, reason: "duplicate" }
    ], context);
    const diff = diffDrafts(before, after);
    expect(diff.records.get(ITCH)!.mark).toBe("changed");
    expect(diff.records.get(ITCH_EXAMPLE)!.mark).toBe("removed");
    expect([...diff.records.values()].map((one) => one.mark)).toContain("added");
    expect(diff.count).toBeGreaterThan(0);
  });

  it("keys every mark to a record the renderer will actually draw", () => {
    // The marks are consumed by a component rendering `articleFromDraft(graph, shown)`, which mints
    // its placeholder ids from positions. If the two disagreed, a mark would silently land on the
    // wrong block — or on nothing.
    const before = draft();
    const { draft: after } = applyOps(before, [
      { op: "add", target: "example", in: ITCH, value: { text: "Me pica todo." } },
      { op: "remove", target: `example:${ITCH_EXAMPLE}`, reason: "duplicate" },
      { op: "set", target: "lexeme", field: "emoji", value: "🌶" }
    ], context);
    const diff = diffDrafts(before, after);
    const rendered = articleFromDraft(graph, diff.shown);
    const drawn = new Set<string>([
      rendered.lexeme.id,
      ...rendered.senses.map((entry) => entry.sense.id),
      ...rendered.senses.flatMap((entry) => entry.examples.map((example) => example.id)),
      ...rendered.attestations.map((attestation) => attestation.id)
    ]);
    for (const key of diff.records.keys()) expect(drawn).toContain(key);
    // And a note key is a position in what will be drawn, not a string that may not be there.
    for (const index of diff.notes.keys()) {
      expect(index).toBeLessThan(diff.shown.notes.length);
    }
    // `order` is what next/previous walks, so it must name every change and nothing else.
    expect([...diff.order].sort()).toEqual(
      [...diff.records.keys(), ...[...diff.notes.keys()].map((index) => `note:${index}`)].sort()
    );
  });

  it("puts a removed record back where it was so it can be drawn struck through", () => {
    const before = draft();
    const { draft: after } = applyOps(before,
      [{ op: "remove", target: `example:${ITCH_EXAMPLE}`, reason: "duplicate" }], context);
    // Gone from what will be saved…
    expect(after.senses.flatMap((sense) => sense.examples).some((item) => item.id === ITCH_EXAMPLE))
      .toBe(false);
    // …and present in what will be shown. Nothing vanishes without being seen going.
    const diff = diffDrafts(before, after);
    const position = before.senses[0].examples.findIndex((item) => item.id === ITCH_EXAMPLE);
    expect(diff.shown.senses[0].examples[position].id).toBe(ITCH_EXAMPLE);
  });

  it("marks a removed sense's examples as removed too", () => {
    const before = draft();
    const { draft: after } = applyOps(before,
      [{ op: "remove", target: `sense:${CHOP}`, reason: "duplicate" }], context);
    const diff = diffDrafts(before, after);
    expect(diff.records.get(CHOP)!.mark).toBe("removed");
    expect(diff.records.get("osd6ieh00s2hxql")!.mark).toBe("removed");
  });

  it("names which of a record's fields moved, not the whole record", () => {
    // Per-field rather than per-record is what lets a tint land on the definition that was reworded
    // instead of on a sense's untouched examples.
    const before = draft();
    const { draft: after } = applyOps(before, [
      { op: "set", target: "lexeme", field: "emoji", value: "🌶" },
      { op: "set", target: `sense:${ITCH}`, field: "domain", value: "medicine" }
    ], context);
    const diff = diffDrafts(before, after);
    expect([...diff.records.get(before.id!)!.fields.keys()]).toEqual(["emoji"]);
    expect([...diff.records.get(ITCH)!.fields.keys()]).toEqual(["domain"]);
  });

  it("marks a note by its position, because text is not an identity", () => {
    const before = draft();
    const { draft: after } = applyOps(before,
      [{ op: "set", target: "lexeme", field: "notes", value: [...before.notes, "Nueva nota."] }], context);
    const diff = diffDrafts(before, after);
    const added = diff.shown.notes.indexOf("Nueva nota.");
    expect(diff.notes.get(added)!.mark).toBe("added");
    // The note that was already there is not marked at all.
    expect(diff.notes.size).toBe(1);
  });

  it("reads a reworded note as one change, with the words that moved", () => {
    // This is the failure that started this round: matched by text, a reworded note had no partner
    // to diff against and came back as a deletion beside an addition.
    const before = draft();
    const reworded = before.notes[0].replace("object", "objeto");
    const { draft: after } = applyOps(before,
      [{ op: "set", target: "lexeme", field: "notes", value: [reworded] }], context);
    const diff = diffDrafts(before, after);
    expect(diff.count).toBe(1);
    const change = diff.notes.get(0)!;
    expect(change.mark).toBe("changed");
    expect(change.words!.some((part) => part.at === "del" && part.text.includes("object"))).toBe(true);
    expect(change.words!.some((part) => part.at === "ins" && part.text.includes("objeto"))).toBe(true);
  });

  it("does not let two identical notes collide", () => {
    // Keyed by text they shared one map entry and one React key; keyed by position they are two.
    const before = draft();
    before.notes = ["La misma nota.", "La misma nota."];
    const { draft: after } = applyOps(before,
      [{ op: "set", target: "lexeme", field: "notes", value: ["La misma nota."] }], context);
    const diff = diffDrafts(before, after);
    expect(diff.shown.notes).toHaveLength(2);
    expect(diff.count).toBe(1);
    expect([...diff.notes.values()].map((one) => one.mark)).toEqual(["removed"]);
  });

  it("marks a sense that only moved, and only the one that moved", () => {
    // A reorder used to produce no marks and a count of zero, over an article that had silently
    // renumbered itself. Rotating two senses moves one of them.
    const before = draft();
    const { draft: after } = applyOps(before,
      [{ op: "reorder", target: "senses", ids: [CHOP, ITCH] }], context);
    const diff = diffDrafts(before, after);
    expect(diff.count).toBe(1);
    const moved = [...diff.records.entries()].filter(([, one]) => one.mark === "moved");
    expect(moved).toHaveLength(1);
    expect(moved[0][1].wasAt).toBeGreaterThan(0);
  });

  it("puts `order` in the order the article draws things", () => {
    // Next and previous have to move down the page, and the article draws notes after senses.
    const before = draft();
    const { draft: after } = applyOps(before, [
      { op: "set", target: `sense:${ITCH}`, field: "domain", value: "medicine" },
      { op: "set", target: "lexeme", field: "notes", value: [...before.notes, "Nueva nota."] }
    ], context);
    const diff = diffDrafts(before, after);
    expect(diff.order[0]).toBe(ITCH);
    expect(diff.order[diff.order.length - 1]).toMatch(/^note:/);
  });

  it("reports no change when nothing moved", () => {
    const before = draft();
    expect(diffDrafts(before, structuredClone(before)).count).toBe(0);
  });
});

describe("counting", () => {
  it("counts a changed note once, not once as a note and again as the head", () => {
    // The notes section marks its lines one by one, so the lexeme head must not also claim the
    // change — "1 change proposed" is what the reader can actually count on the page.
    const before = draft();
    const { draft: after } = applyOps(before,
      [{ op: "set", target: "lexeme", field: "notes", value: [...before.notes, "Nueva nota."] }], context);
    const diff = diffDrafts(before, after);
    expect(diff.count).toBe(1);
    expect(diff.records.get(before.id!)).toBeUndefined();
  });

  it("counts a head change and a note change separately", () => {
    const before = draft();
    const { draft: after } = applyOps(before, [
      { op: "set", target: "lexeme", field: "emoji", value: "🌶" },
      { op: "set", target: "lexeme", field: "notes", value: [...before.notes, "Nueva nota."] }
    ], context);
    expect(diffDrafts(before, after).count).toBe(2);
  });
});

describe("a second turn, built on the first", () => {
  it("can address a record the previous turn added", () => {
    /* The bug this exists for: "add an example", then "make that example more concrete". The added
       example used to carry no id, so it had no name in the document the second turn was given —
       the model invented one and the whole proposal was refused. */
    const before = draft();
    const first = applyOps(before,
      [{ op: "add", target: "example", in: ITCH, value: { text: "Me pica la espalda." } }], context);
    const added = first.draft.senses[0].examples.at(-1)!;
    expect(added.id).toMatch(/^[a-z0-9]{15}$/);

    // The document the next turn sees names it, so the next turn can edit it.
    expect(yamlForDraft(first.draft)).toContain(added.id!);
    const second = applyOps(first.draft, [
      { op: "set", target: `example:${added.id}`, field: "text", value: "Me pica mucho la espalda." }
    ], context);
    expect(second.draft.senses[0].examples.at(-1)!.text).toBe("Me pica mucho la espalda.");
  });

  it("shows the reader one change, not two, when a turn edits what the last one added", () => {
    // The comparison stays against the stored document, so the bar counts what is outstanding.
    const origin = draft();
    const first = applyOps(origin,
      [{ op: "add", target: "example", in: ITCH, value: { text: "Me pica la espalda." } }], context);
    const added = first.draft.senses[0].examples.at(-1)!;
    const second = applyOps(first.draft, [
      { op: "set", target: `example:${added.id}`, field: "text", value: "Me pica mucho." }
    ], context);
    const diff = diffDrafts(origin, second.draft);
    expect(diff.count).toBe(1);
    expect(diff.records.get(added.id!)!.mark).toBe("added");
  });
});

describe("the loop line, which chat may change like any other lexeme field", () => {
  it("applies a change to either field and marks the lexeme as changed", () => {
    const before = draft();
    const { draft: after } = applyOps(before, [
      { op: "set", target: "lexeme", field: "primaryGloss", value: "to itch" },
      { op: "set", target: "lexeme", field: "emotion", value: "prickly and restless" }
    ], context);
    expect(after.primaryGloss).toBe("to itch");
    expect(after.emotion).toBe("prickly and restless");
    // One table drives both `applyOps` and the change marks, so a field chat can set is a field the
    // reader sees marked — there is no way to add one and get only half.
    const diff = diffDrafts(before, after);
    expect(diff.records.get(PICAR)!.mark).toBe("changed");
    expect(diff.count).toBeGreaterThan(0);
  });

  it("lets either be cleared to null, which is what most words carry", () => {
    const { draft: after } = applyOps(draft(), [
      { op: "set", target: "lexeme", field: "primaryGloss", value: null }
    ], context);
    expect(after.primaryGloss).toBeNull();
  });

  it("names both in the table the prompt is told about", () => {
    expect(Object.keys(SETTABLE.lexeme)).toContain("primaryGloss");
    expect(Object.keys(SETTABLE.lexeme)).toContain("emotion");
  });
});

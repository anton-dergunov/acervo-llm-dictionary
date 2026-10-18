"""The cases: a document, a conversation, what the last turn asks for, and how to tell it was done.

A case is scored end to end, the way the owner meets it: the model's answer is shaped by the
server's `_shaped`, the proposal is applied by the device's `applyOps` (through `checker.ts`), and
the applied draft is then checked against what the turn actually asked for. A proposal that applies
but edits the wrong field is a failure, and so is a question answered with an edit nobody wanted.

`expect` is the gate:

- `edit`   — the turn asks for a change; success needs a proposal that applies and passes `check`.
- `answer` — a question; success is no proposal at all.
- `either` — no proposal is fine; a proposal is fine if it applies and passes `check`. Used for the
  ambiguous turn and the light adversarial cases, where the point is that nothing *breaks*, not that
  the model takes one particular side.

Checks return a list of problems, each one short sentence; empty is a pass. `minor` problems — an
emphasis lost, a duplicated gloss term — are reported apart and do not fail a case: they are worth
knowing and not worth a turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
DOCUMENTS = HERE / "documents"

Draft = dict[str, Any]


@dataclass(frozen=True)
class Outcome:
    """What a check is given: the draft before, the draft after, and the operations sent."""

    before: Draft
    after: Draft
    ops: list[dict[str, Any]]


@dataclass(frozen=True)
class Verdict:
    problems: list[str] = field(default_factory=list)
    minor: list[str] = field(default_factory=list)


Check = Callable[[Outcome], Verdict]


@dataclass(frozen=True)
class Case:
    id: str
    split: str          # "replay" | "dev" | "held"
    category: str
    document: str       # a file in documents/
    turns: tuple[dict[str, Any], ...]
    expect: str         # "edit" | "answer" | "either"
    check: Check | None = None
    focus: str | None = None
    note: str = ""
    # For the light adversarial cases: the device refusing the proposal with a sentence is a pass,
    # because refusing is exactly what keeps the article intact.
    refusal_ok: bool = False

    def text(self) -> str:
        return (DOCUMENTS / self.document).read_text(encoding="utf-8")


def you(text: str) -> dict[str, str]:
    return {"role": "you", "text": text}


def acervo(text: str, **offered: Any) -> dict[str, Any]:
    turn: dict[str, Any] = {"role": "acervo", "text": text}
    if offered:
        turn["offered"] = offered
    return turn


# ── reading a draft ───────────────────────────────────────────────────────────

def senses(draft: Draft) -> list[Draft]:
    return draft.get("senses") or []


def sense(draft: Draft, sense_id: str) -> Draft | None:
    return next((item for item in senses(draft) if item.get("id") == sense_id), None)


def examples(draft: Draft) -> list[Draft]:
    return [example for item in senses(draft) for example in item.get("examples") or []]


def example(draft: Draft, example_id: str) -> Draft | None:
    return next((item for item in examples(draft) if item.get("id") == example_id), None)


def terms(record: Draft | None, lang: str | None = None) -> list[str]:
    if not record:
        return []
    return [term for group in record.get("glosses") or []
            if lang is None or group.get("lang") == lang for term in group.get("terms") or []]


def learner_text(draft: Draft) -> list[tuple[str, str]]:
    """Every field written in the learner's languages, as (where, text)."""
    out: list[tuple[str, str]] = []
    for name in ("shortGloss", "primaryGloss"):
        if draft.get(name):
            out.append((name, draft[name]))
    for index, line in enumerate(draft.get("notes") or []):
        out.append((f"notes[{index}]", line))
    for item in senses(draft):
        for term in terms(item):
            out.append((f"sense:{item.get('id')}.glosses", term))
        for ex in item.get("examples") or []:
            for name in ("translation", "matchedTranslationForm"):
                if ex.get(name):
                    out.append((f"example:{ex.get('id')}.{name}", ex[name]))
    for att in draft.get("attestations") or []:
        if att.get("translation"):
            out.append((f"attestation:{att.get('id')}.translation", att["translation"]))
    return out


def word_text(draft: Draft) -> dict[str, Any]:
    """Every field written in the word's own language, which a translation edit must not touch."""
    out: dict[str, Any] = {"headword": draft.get("headword"), "lemma": draft.get("lemma"),
                           "reading": draft.get("reading"), "language": draft.get("language")}
    for item in senses(draft):
        if item.get("definitionLang") == draft.get("language"):
            out[f"sense:{item.get('id')}.definition"] = item.get("definition")
        for ex in item.get("examples") or []:
            out[f"example:{ex.get('id')}.text"] = ex.get("text")
            out[f"example:{ex.get('id')}.matchedForm"] = ex.get("matchedForm")
    for att in draft.get("attestations") or []:
        out[f"attestation:{att.get('id')}.text"] = att.get("text")
    return out


def records(draft: Draft) -> dict[str, Draft]:
    """Every addressable record by key, the lexeme head without its children."""
    out: dict[str, Draft] = {"lexeme": {k: v for k, v in draft.items()
                                        if k not in ("senses", "attestations", "images")}}
    for item in senses(draft):
        out[f"sense:{item.get('id')}"] = {k: v for k, v in item.items() if k != "examples"}
        for ex in item.get("examples") or []:
            out[f"example:{ex.get('id')}"] = ex
    for att in draft.get("attestations") or []:
        out[f"attestation:{att.get('id')}"] = att
    return out


def changed_keys(before: Draft, after: Draft) -> set[str]:
    one, other = records(before), records(after)
    return {key for key in one.keys() | other.keys() if one.get(key) != other.get(key)}


# ── composable checks ─────────────────────────────────────────────────────────

def all_of(*checks: Check) -> Check:
    def run(outcome: Outcome) -> Verdict:
        problems: list[str] = []
        minor: list[str] = []
        for check in checks:
            verdict = check(outcome)
            problems += verdict.problems
            minor += verdict.minor
        return Verdict(problems, minor)
    return run


def only_touches(*allowed: str) -> Check:
    """No record outside `allowed` changed. `lexeme` is the head; `new` allows added records."""
    def run(outcome: Outcome) -> Verdict:
        before_keys = set(records(outcome.before))
        stray = []
        for key in sorted(changed_keys(outcome.before, outcome.after)):
            if key in allowed:
                continue
            if "new" in allowed and key not in before_keys:
                continue
            stray.append(key)
        return Verdict([f"touched {', '.join(stray)}, which the turn did not ask about"] if stray else [])
    return run


def word_language_untouched(outcome: Outcome) -> Verdict:
    before, after = word_text(outcome.before), word_text(outcome.after)
    moved = [key for key in before if key in after and before[key] != after[key]]
    return Verdict([f"changed {', '.join(moved)}, which is in the word's own language"] if moved else [])


def replaced(old: str, new: str, where: tuple[str, ...]) -> Check:
    """`old` is gone from every learner-language field, and `new` is in each of `where`."""
    def run(outcome: Outcome) -> Verdict:
        problems: list[str] = []
        minor: list[str] = []
        left = [place for place, text in learner_text(outcome.after) if old.casefold() in text.casefold()]
        if left:
            problems.append(f"«{old}» is still in {', '.join(left)}")
        texts = learner_text(outcome.after)
        for place in where:
            if not any(p == place and new.casefold() in t.casefold() for p, t in texts):
                problems.append(f"«{new}» is not in {place}")
        for name in ("shortGloss",):
            value = outcome.after.get(name) or ""
            parts = [part.strip().casefold() for part in value.replace(",", ";").split(";") if part.strip()]
            if len(parts) != len(set(parts)):
                minor.append(f"{name} repeats a term: {value}")
        for ex in examples(outcome.before):
            now = example(outcome.after, ex.get("id"))
            if now and ex.get("matchedTranslationForm") and not now.get("matchedTranslationForm"):
                minor.append(f"example:{ex.get('id')} lost its translation emphasis")
        return Verdict(problems, minor)
    return run


# ── the real case: «абиссальный» → «бездонный», 2026-10-16 ──────────────────

ABYSSAL = "abyssal.yaml"
AB_SENSE1, AB_SENSE2 = "lgksiv0a4adcaar", "z5aouusz9u6bbj4"
AB_EX1, AB_EX2 = "pvs056rz7zyuix1", "pl491uiy3zasd85"

# Verbatim, as the owner pasted it from the open window — including the typographic apostrophe.
T1 = "абиссальный - is there such word in Russian?"
R1 = ("Да, слово «абиссальный» есть в русском языке. Оно используется главным образом в научной "
      "литературе и океанологии для обозначения того, что относится к огромным глубинам океана. "
      "Происходит от греческого слова *abyssos* (бездонный).")
T2 = ("so better replace with бездонный, because I guess it can be replaced in this vocabulary item? "
      "for example as well.")
R2 = ("Слово «абиссальный» в русском языке существует, но оно узкоспециальное (научное). Если вы "
      "хотите чаще использовать более живое и понятное слово «бездонный» (или «глубоководный»), их "
      "можно добавить как основные глоссы или использовать в примерах. Но полностью заменять "
      "«абиссальный» не обязательно, так как это точный перевод английского термина *abyssal*.")
T3 = "It is better if we just change абиссальный to бездонный everywhere in this article. Do this."
R3 = ("I have updated the headword, lemma, short and primary glosses, and all references to use "
      "«бездонный» instead of «абиссальный».")
T4 = "Don’t rewrite, update."

ABYSSAL_EVERYWHERE = all_of(
    word_language_untouched,
    only_touches("lexeme", f"sense:{AB_SENSE1}", f"example:{AB_EX1}"),
    replaced("абиссальн", "бездонн",
             ("primaryGloss", f"sense:{AB_SENSE1}.glosses", f"example:{AB_EX1}.translation")),
)

REPLAY: list[Case] = [
    Case("replay-t1", "replay", "question", ABYSSAL, (you(T1),), "answer"),
    Case("replay-t2", "replay", "replace", ABYSSAL, (you(T1), acervo(R1), you(T2)), "either",
         ABYSSAL_EVERYWHERE, note="ambiguous: a question and a request at once"),
    Case("replay-t3", "replay", "replace", ABYSSAL,
         (you(T1), acervo(R1), you(T2), acervo(R2), you(T3)), "edit", ABYSSAL_EVERYWHERE),
    Case("replay-t4", "replay", "replace", ABYSSAL,
         (you(T1), acervo(R1), you(T2), acervo(R2), you(T3), acervo(R3), you(T4)), "edit",
         ABYSSAL_EVERYWHERE, note="the transcript as shipped: nothing says turn 3 was refused"),
]


# ── the wider set ──────────────────────────────────────────────────────────────

def that(description: str, predicate: Callable[[Outcome], bool]) -> Check:
    """One plain assertion about the applied draft; `description` is what failing it means."""
    def run(outcome: Outcome) -> Verdict:
        try:
            ok = bool(predicate(outcome))
        except (KeyError, IndexError, TypeError, AttributeError):
            ok = False
        return Verdict([] if ok else [description])
    return run


def identity_kept(outcome: Outcome) -> Verdict:
    keys = ("language", "headword")
    moved = [key for key in keys if outcome.before.get(key) != outcome.after.get(key)]
    return Verdict([f"changed {', '.join(moved)}"] if moved else [])


def added_examples(outcome: Outcome) -> list[Draft]:
    held = {item.get("id") for item in examples(outcome.before)}
    return [item for item in examples(outcome.after) if item.get("id") not in held]


def in_sense(outcome: Outcome, sense_id: str) -> list[Draft]:
    found = sense(outcome.after, sense_id)
    return found.get("examples") or [] if found else []


def tr(outcome: Outcome, example_id: str) -> str:
    return (example(outcome.after, example_id) or {}).get("translation") or ""


def txt(outcome: Outcome, example_id: str) -> str:
    return (example(outcome.after, example_id) or {}).get("text") or ""


def cyrillic(text: str) -> bool:
    return any("а" <= letter.lower() <= "я" or letter.lower() == "ё" for letter in text)


AB, DI, DI2, PI, BA, ES, TU, RE, AP = ("abyssal.yaml", "disfraz.yaml", "disfraz-added.yaml",
                                       "picar.yaml", "balsa.yaml", "espolvorear.yaml", "turmoil.yaml",
                                       "reckless.yaml", "aprovechar.yaml")
DI_SENSE, DI_EX, DI_NEW = "kq2m7x1p4vd9r0s", "b8n4k2j7w1q5z0c", "k3x9p2m7q1w8z4a"
PI_ITCH, PI_CHOP, PI_EX1, PI_EX2 = "sensepicaritch0", "sensepicarchop0", "examplepicar010", "osd6ieh00s2hxql"
BA_SENSE, BA_EX = "sensebalsaraft0", "examplebalsa010"
ES_SENSE = "senseespolvor10"
RE_S1, RE_S2 = "senserecklessa1", "senserecklessb2"
RE_EX1, RE_EX2, RE_EX3, RE_EX4 = "examplereckles1", "examplereckles2", "examplereckles3", "examplereckles4"
AP_S1, AP_S2 = "senseaprovech01", "senseaprovech02"
AP_EX1, AP_EX2, AP_EX3 = "exampleaprove01", "exampleaprove02", "exampleaprove03"

WIDER: list[Case] = [
    # Replace words — the failure class the owner hit.
    Case("rep-ab-precise", "dev", "replace", AB,
         (you("Replace «абиссальный» with «бездонный» in the Russian glosses and translations."),),
         "edit", ABYSSAL_EVERYWHERE),
    Case("rep-ab-short", "held", "replace", AB, (you("use бездонный instead of абиссальный"),),
         "edit", ABYSSAL_EVERYWHERE),
    Case("rep-di-outfit", "dev", "replace", DI,
         (you("Use «outfit» instead of «costume» everywhere."),), "edit",
         all_of(word_language_untouched,
                only_touches("lexeme", f"sense:{DI_SENSE}", f"example:{DI_EX}"),
                replaced("costume", "outfit", ("shortGloss", f"sense:{DI_SENSE}.glosses",
                                                f"example:{DI_EX}.translation")))),
    Case("rep-pi-mince", "held", "replace", PI,
         (you("Use «to mince» instead of «to dice»."),), "edit",
         all_of(word_language_untouched, only_touches(f"sense:{PI_CHOP}"),
                that("«to mince» is not a gloss of the chopping sense",
                     lambda o: "to mince" in terms(sense(o.after, PI_CHOP))),
                that("«to dice» is still a gloss",
                     lambda o: "to dice" not in terms(sense(o.after, PI_CHOP))),
                that("«to chop» was lost", lambda o: "to chop" in terms(sense(o.after, PI_CHOP))))),
    Case("rep-re-everywhere", "dev", "replace", RE,
         (you("Replace безрассудный with опрометчивый everywhere."),), "edit",
         all_of(word_language_untouched,
                replaced("безрассудн", "опрометчив",
                         (f"sense:{RE_S1}.glosses", f"sense:{RE_S2}.glosses",
                          f"example:{RE_EX1}.translation", f"example:{RE_EX4}.translation"))),
         note="the word sits in seven records, in four inflected forms"),
    Case("rep-ba-definition", "held", "replace", BA,
         (you("In the definition, replace «plana» with «de troncos»."),), "edit",
         all_of(only_touches(f"sense:{BA_SENSE}"),
                that("the definition does not say «de troncos»",
                     lambda o: "de troncos" in sense(o.after, BA_SENSE)["definition"]),
                that("the definition still says «plana»",
                     lambda o: "plana" not in sense(o.after, BA_SENSE)["definition"]))),
    Case("rep-ap-first-example", "dev", "replace", AP,
         (you("In the first example's translation, use «make the most of» instead of «take advantage of»."),),
         "edit",
         all_of(word_language_untouched, only_touches(f"example:{AP_EX1}"),
                that("the first translation does not say «make the most of»",
                     lambda o: "make the most of" in tr(o, AP_EX1).lower()),
                that("the first translation still says «take advantage of»",
                     lambda o: "take advantage" not in tr(o, AP_EX1).lower()))),
    Case("rep-tu-primary", "held", "replace", TU,
         (you("The primary gloss is in English — it should be Russian."),), "edit",
         all_of(word_language_untouched, only_touches("lexeme"),
                that("primaryGloss is not Russian", lambda o: cyrillic(o.after.get("primaryGloss") or "")))),

    # Reword.
    Case("rew-ab-stiff", "dev", "reword", AB,
         (you("About the example «She stared into an abyssal darkness.»: this translation is stiff, make it more natural."),),
         "edit",
         all_of(word_language_untouched, only_touches(f"example:{AB_EX2}"),
                that("the translation did not change",
                     lambda o: tr(o, AB_EX2) != "Она вглядывалась в бездонную темноту.")),
         focus=f"example:{AB_EX2}"),
    Case("rew-pi-definition", "held", "reword", PI,
         (you("Make the definition of the chopping sense simpler."),), "edit",
         all_of(only_touches(f"sense:{PI_CHOP}"),
                that("the definition did not change",
                     lambda o: sense(o.after, PI_CHOP)["definition"] != "Cortar en trozos pequeños."))),
    Case("rew-re-simpler-example", "dev", "reword", RE,
         (you("Make the second example simpler and shorter."),), "edit",
         all_of(only_touches(f"example:{RE_EX2}"),
                that("the second example is not shorter",
                     lambda o: 0 < len(txt(o, RE_EX2)) < len("It was reckless of her to swim so far out alone, given how strong the current was that afternoon.")),
                that("the second example lost the word",
                     lambda o: "reckless" in txt(o, RE_EX2).lower()))),
    Case("rew-re-shorter-note", "held", "reword", RE,
         (you("Make the first note shorter."),), "edit",
         all_of(only_touches("lexeme"),
                that("the notes are not two, first shorter, second kept",
                     lambda o: len(o.after["notes"]) == 2
                     and len(o.after["notes"][0]) < len(o.before["notes"][0])
                     and o.after["notes"][1] == o.before["notes"][1]))),
    Case("rew-ap-typo", "dev", "reword", AP,
         (you("There's a typo in the first example: «tienpo»."),), "edit",
         all_of(only_touches(f"example:{AP_EX1}"),
                that("the typo is still there or the sentence changed otherwise",
                     lambda o: txt(o, AP_EX1) == "Aprovecha el tiempo mientras puedas."),
                that("the emphasis on «Aprovecha» was lost",
                     lambda o: example(o.after, AP_EX1)["matchedForm"] == "Aprovecha"))),
    Case("rew-re-wrong-translation", "held", "reword", RE,
         (you("The translation of the third example is wrong."),), "edit",
         all_of(word_language_untouched, only_touches(f"example:{RE_EX3}"),
                that("the translation still says «Осторожные»",
                     lambda o: "осторожн" not in tr(o, RE_EX3).lower() and tr(o, RE_EX3)))),

    # Add.
    Case("add-di-shop", "dev", "add", DI, (you("Give me one more example, in a shop."),), "edit",
         all_of(only_touches("new"),
                that("not exactly one new example under the sense",
                     lambda o: len(added_examples(o)) == 1 and len(in_sense(o, DI_SENSE)) == 2),
                that("the new example does not use the word",
                     lambda o: "disfra" in added_examples(o)[0]["text"].lower()))),
    Case("add-ba-attestation", "held", "add", BA,
         (you("I read this in a book: «La balsa se hundió a mitad del lago.»"),), "edit",
         all_of(only_touches("new"),
                that("no attestation carries the sentence",
                     lambda o: any("se hundió a mitad del lago" in (a.get("text") or "")
                                   for a in o.after.get("attestations") or [])),
                that("no example is drawn from that attestation",
                     lambda o: any(e.get("sourceAttestationId") and e.get("origin") == "attestation"
                                   for e in added_examples(o))))),
    Case("add-pi-gloss-term", "dev", "add", PI,
         (you("Add «to sting» as another translation of the itching sense."),), "edit",
         all_of(only_touches(f"sense:{PI_ITCH}"),
                that("the itching sense lacks «to sting» or lost «to itch»",
                     lambda o: {"to sting", "to itch"} <= set(terms(sense(o.after, PI_ITCH)))))),
    Case("add-ab-note", "held", "add", AB,
         (you("Add a note that «бездонный» is the everyday word and «абиссальный» is scientific."),),
         "edit",
         all_of(only_touches("lexeme"),
                that("the notes are not the old one plus one new",
                     lambda o: len(o.after["notes"]) == 2 and o.before["notes"][0] in o.after["notes"]))),
    Case("add-es-sense", "dev", "add", ES,
         (you("Add a figurative sense: to sprinkle a speech or text with jokes or quotes."),), "edit",
         all_of(only_touches("new"),
                that("not exactly one new sense, the old one first",
                     lambda o: len(senses(o.after)) == 2 and senses(o.after)[0].get("id") == ES_SENSE))),
    Case("add-re-example-sense2", "held", "add", RE,
         (you("Add an example to the second sense."),), "edit",
         all_of(only_touches("new"),
                that("not exactly one new example, under the second sense",
                     lambda o: len(added_examples(o)) == 1 and len(in_sense(o, RE_S2)) == 2))),
    Case("add-ap-missing-translation", "dev", "add", AP,
         (you("The second example has no translation — add one."),), "edit",
         all_of(word_language_untouched, only_touches(f"example:{AP_EX2}"),
                that("the second example still has no translation", lambda o: tr(o, AP_EX2)))),
    Case("add-di-russian", "held", "add", DI,
         (you("Add Russian translations to the glosses too."),), "edit",
         all_of(only_touches(f"sense:{DI_SENSE}", "lexeme"),
                that("the sense has no Russian gloss group or lost the English one",
                     lambda o: terms(sense(o.after, DI_SENSE), "ru")
                     and {"costume", "disguise"} <= set(terms(sense(o.after, DI_SENSE), "en"))))),

    # Remove.
    Case("rem-ab-second-example", "dev", "remove", AB, (you("Drop the second example."),), "edit",
         all_of(only_touches(f"example:{AB_EX2}"),
                that("the second example is still there", lambda o: example(o.after, AB_EX2) is None),
                that("the first example went too", lambda o: example(o.after, AB_EX1) is not None))),
    Case("rem-pi-gloss-term", "held", "remove", PI, (you("Remove «to dice» from the glosses."),),
         "edit",
         all_of(only_touches(f"sense:{PI_CHOP}"),
                that("«to dice» is still there or «to chop» went",
                     lambda o: terms(sense(o.after, PI_CHOP)) == ["to chop"]))),
    Case("rem-re-note", "dev", "remove", RE, (you("Delete the second note."),), "edit",
         all_of(only_touches("lexeme"),
                that("the notes are not just the first one",
                     lambda o: o.after["notes"] == o.before["notes"][:1]))),
    Case("rem-ab-sense2", "held", "remove", AB, (you("Remove the second meaning."),), "edit",
         all_of(only_touches(f"sense:{AB_SENSE2}", f"example:{AB_EX2}"),
                that("the second sense is still there or the first went",
                     lambda o: [x.get("id") for x in senses(o.after)] == [AB_SENSE1]))),

    # Head fields.
    Case("head-ba-emoji", "dev", "head", BA, (you("Use 🌊 as the emoji."),), "edit",
         all_of(only_touches("lexeme"), that("the emoji is not 🌊", lambda o: o.after.get("emoji") == "🌊"))),
    Case("head-pi-register", "held", "head", PI, (you("Mark it as informal."),), "edit",
         all_of(only_touches("lexeme"),
                that("the register is not colloquial, the value for informal",
                     lambda o: o.after.get("register") == "colloquial"))),
    Case("head-re-ipa", "dev", "head", RE, (you("The IPA is wrong, it should be /ˈrekləs/."),), "edit",
         all_of(only_touches("lexeme"),
                that("the IPA is not /ˈrekləs/", lambda o: "rekləs" in (o.after.get("ipa") or "").replace(".", "")))),
    Case("head-ab-reorder", "held", "head", AB, (you("Put the second meaning first."),), "edit",
         all_of(word_language_untouched,
                that("the senses are not swapped",
                     lambda o: [x.get("id") for x in senses(o.after)] == [AB_SENSE2, AB_SENSE1]),
                that("a sense changed besides its order",
                     lambda o: all({k: v for k, v in x.items() if k != "order"}
                                   == {k: v for k, v in sense(o.before, x["id"]).items() if k != "order"}
                                   for x in senses(o.after))))),

    # Questions: an answer, and no proposal.
    Case("q-ab-good", "dev", "question", AB, (you("Is «бездонный» a good translation here?"),), "answer"),
    Case("q-di-difference", "held", "question", DI,
         (you("What is the difference between «el disfraz» and «el traje»?"),), "answer"),
    Case("q-pi-error", "dev", "question", PI,
         (you("Is «Producir comezón» actually an error?"),), "answer"),
    Case("q-re-remember", "held", "question", RE, (you("How do I remember it?"),), "answer"),
    Case("q-ba-common", "dev", "question", BA, (you("Is it common?"),), "answer"),
    Case("q-pi-form", "held", "question", PI,
         (you("Why is it «me pica» and not «yo pico»?"),), "answer"),

    # Multi-turn.
    Case("multi-di-shorten-new", "dev", "multi", DI2,
         (you("Give me one more example, at a party."),
          acervo("Here is one more example, at a party: «Alquiló un disfraz de médico para la fiesta "
                 "de anoche en casa de Marta, que fue enorme.»",
                 summary="Adds an example at a party under sense 1.", outcome="applied"),
          you("Make that new example shorter.")),
         "edit",
         all_of(only_touches(f"example:{DI_NEW}"),
                that("the new example is not shorter or lost the word",
                     lambda o: 0 < len(txt(o, DI_NEW)) < len(txt(Outcome(o.before, o.before, []), DI_NEW))
                     and "disfraz" in txt(o, DI_NEW).lower())),
         note="addresses the id minted for the example added a turn ago"),
    Case("multi-ab-after-refusal", "held", "multi", AB,
         (you(T3),
          acervo("Here is a change that uses «бездонный» instead of «абиссальный» throughout.",
                 summary="Replaces «абиссальный» with «бездонный» in the headword, lemma and glosses.",
                 outcome="refused",
                 reason="That was a rewrite rather than an edit, so nothing was changed."),
          you("Try again, smaller.")),
         "edit", ABYSSAL_EVERYWHERE),

    # Light adversarial: nothing may break, and declining is as good as complying.
    Case("adv-re-remove-all", "dev", "adversarial", RE, (you("Remove everything in this article."),),
         "either", identity_kept, refusal_ok=True),
    Case("adv-pi-rewrite", "held", "adversarial", PI,
         (you("Rewrite this whole entry from scratch, every field, much better."),), "either",
         identity_kept, refusal_ok=True),
    Case("adv-ba-french", "dev", "adversarial", BA,
         (you("Translate the whole article into French."),), "either", identity_kept, refusal_ok=True),
    Case("adv-ab-language", "held", "adversarial", AB,
         (you("Change the language of this entry to Russian."),), "either", identity_kept,
         refusal_ok=True),
]

CASES: list[Case] = [*REPLAY, *WIDER]


def by_id() -> dict[str, Case]:
    return {case.id: case for case in CASES}

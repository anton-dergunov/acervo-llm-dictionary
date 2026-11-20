"""Model call two: build the article.

It returns the model that answered alongside the article, because under a provider chain that is
not knowable before the call: a 429 at the first row is answered by the second, and the locked
contract is that the entry records the model that *answered*. Reading it from the configuration
instead — which is what this route did while there was only ever one provider — would leave
`modelId` naming a model that produced nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from acervo.models import Answer, journal
from acervo.models.call import HEDGE_SECONDS
from acervo.repository import model_selection
from acervo.services.capture.coerce import reference_of, text_list, trimmed
from acervo.services.capture.dictionary_check import keys_for
from acervo.services.capture.vet import Vetted, vet
from acervo.services.dictionaries.lookup import articles_for
from acervo.services.models import llm_json
from acervo.services.prompts import prompt_text
from acervo.services.reader import reader_section
from acervo.services.rules import with_rules
from acervo.settings import Settings


def build_user_message(
    resolution: dict[str, Any],
    request: dict[str, Any],
    vocabulary: dict[str, Any],
    topics: list[dict[str, Any]],
) -> str:
    """Everything the model is told about this word, beside the prompt itself.

    Lifted out of `compose` so that a measurement can send the *shipped* request rather than a copy
    of it — `experiments/compose-lesson-line/` compares two versions of the prompt, and a second
    implementation of this assembly would quietly be part of what it measured.
    """
    reference = reference_of(request)
    names = {topic["name"].lower(): topic["name"] for topic in topics}
    preferred = [names[name.lower()] for name in text_list(request.get("topics")) if name.lower() in names]
    gloss_langs = vocabulary["glossLangs"]
    sentences = resolution["sentences"]

    user = "\n".join(
        line
        for line in [
            "Language: " + resolution["language"],
            "Headword: " + resolution["headword"],
            "Lemma: " + resolution["lemma"],
            "Part of speech: " + resolution["pos"],
            "Define senses in: " + vocabulary["definitionLang"],
            "Gloss into: " + ", ".join(gloss_langs),
            "Write notes in: " + (vocabulary.get("notesLang") or gloss_langs[0]),
            "Topics to choose from: "
            + (" | ".join(topic["name"] for topic in topics) if topics else "(none — return an empty list)"),
            # A file of notes already filed under one heading knows its own topic better than the
            # model can infer it from a single word, so say so — as a preference, not an instruction.
            "The learner already files these under: "
            + ", ".join(preferred)
            + ". Prefer that unless it is plainly wrong."
            if preferred
            else "",
            "",
            "Sentences the learner supplied (index them from 0 for `fromSentence`):",
            "\n".join(
                f"{index}: {item['text']}" + (f"  —  {item['translation']}" if item["translation"] else "")
                for index, item in enumerate(sentences)
            )
            if sentences
            else "(none)",
            f"\nThe learner asks specifically: {trimmed(request.get('note'))}"
            if trimmed(request.get("note"))
            else "",
            "\nReference entry from an external dictionary, which the learner was reading when\n"
            "they asked for this. Ground the article on it. Its example sentences are the dictionary's,\n"
            "NOT sentences the learner supplied:\n```\n" + reference["text"] + "\n```"
            if reference
            else "",
            "\nTreatment: STAY CLOSE TO THE REFERENCE. Carry over its senses and no others, in its\n"
            "order. Translate and tidy; do not add senses, examples or notes it does not have."
            if reference and reference["mode"] == "faithful"
            else "",
            "\nTreatment: FILL IN THE GAPS. Keep what the reference says right, condense it to the three\n"
            "to five senses worth reading, and add what it lacks — glosses, an example where the word\n"
            "needs one, a note on usage, an emoji."
            if reference and reference["mode"] == "expand"
            else "",
        ]
        if line != ""
    )
    return user


def compose_parts(
    prompts: Path,
    dictionaries: Path,
    resolution: dict[str, Any],
    request: dict[str, Any],
    vocabulary: dict[str, Any],
    topics: list[dict[str, Any]],
    *,
    checking: bool = True,
) -> tuple[str, str, Callable[[Any], Vetted]]:
    """The system prompt before the owner's standing rules, the user message and the check.

    Everything compose sends and judges that needs no database, so the starter builder
    (`scripts/starter/`) asks a model exactly what compose asks and checks the reply the same way.
    """
    section = reader_section(vocabulary)
    template = prompt_text(prompts, "acervo_compose")
    system = f"{template}\n\n{section}" if section else template
    user = build_user_message(resolution, request, vocabulary, topics)
    # The dictionaries are read once here, not once per pair.
    found = articles_for(dictionaries, resolution["language"],
                         keys_for(resolution["headword"], resolution["lemma"])) if checking else []
    return system, user, vet(vocabulary, resolution, found, checking)


def compose(
    settings: Settings,
    owner: str,
    resolution: dict[str, Any],
    request: dict[str, Any],
    vocabulary: dict[str, Any],
    topics: list[dict[str, Any]],
) -> tuple[dict[str, Any], Answer]:
    # Judged inside the walk (`vet.py`): a model whose answer could not become a draft, is in the
    # wrong language or disagrees with an installed dictionary is passed over and the next pair in
    # the order answers.
    checking = model_selection.check_answers(owner)
    system, user, check = compose_parts(settings.prompts_path, settings.dictionaries_path, resolution,
                                        request, vocabulary, topics, checking=checking)
    vetted, call = llm_json(
        settings, owner, with_rules(system, owner), user,
        caller="compose", hedge_after=HEDGE_SECONDS, check=check,
    )
    assert isinstance(vetted, Vetted)
    if not checking:
        # So `admin calls` can tell an answer nobody checked from one that passed.
        journal.outcome("compose", pair=f"{call.provider_id}:{call.model}", checks="off")
    elif vetted.fixed or vetted.dropped:
        # Counted per model, so `admin calls` can say how often each one needs correcting, and where.
        journal.outcome("compose", pair=f"{call.provider_id}:{call.model}",
                        fixed=",".join(vetted.fixed), dropped=",".join(vetted.dropped))
    return vetted.answer, call

"""The owner's standing rules, and the one place they are joined to a prompt.

Settings ▸ Rules is free text — "I am vegan, so never show or mention meat", "no profanity in examples"
— and it reaches every text call that writes something the owner will read: entries, the article
conversation, picture briefs, stories and the choice of clips. Not the resolver, which only names
the word a scrap of text is about, and not narration, which cuts a story into passages and may not
change a word of it. Voices and image models are never given it: what they draw and say is what a
text call already wrote.

`with_rules` is applied here, in the binding layer, to text a service already loaded, so the
enrichment packages are handed a prompt and never learn where part of it came from.
"""

from __future__ import annotations

from typing import Any

from acervo.errors import ApiError
from acervo.repository import prompt_rules

LIMIT = 4000

# Said once, after everything else the prompt asks for, so the rules can steer what is written and
# cannot be read as a change to the shape of the answer.
_HEADING = "## The reader's standing rules"
_PREAMBLE = (
    "The person you are writing for has set these rules for everything written for them. Follow "
    "them in what you choose to write about — subjects, scenes, examples, register — and never let "
    "them change the shape of the answer asked for above."
)


def with_rules(text: str, owner: str) -> str:
    """The prompt with the owner's rules as its last section, or the prompt untouched if none."""
    rules = prompt_rules.settings(owner).rules.strip()
    if not rules:
        return text
    return f"{text}\n\n{_HEADING}\n\n{_PREAMBLE}\n\n{rules}"


def settings_view(owner: str) -> dict[str, Any]:
    return {**prompt_rules.settings(owner), "limit": LIMIT}


def apply_settings(owner: str, body: dict[str, Any]) -> dict[str, Any]:
    rules = body.get("rules")
    if not isinstance(rules, str):
        raise ApiError(400, "invalid_input", "rules must be text.")
    rules = rules.strip()
    if len(rules) > LIMIT:
        raise ApiError(400, "invalid_input", f"Rules may be at most {LIMIT} characters.")
    prompt_rules.save(owner, rules=rules)
    return settings_view(owner)

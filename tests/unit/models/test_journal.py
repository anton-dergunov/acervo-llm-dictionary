"""What the model layer writes down, and what it must never write down.

The regression this exists for took two deployments to find because nothing recorded that a chain
had walked nine pairs and been refused by every one for the same reason. The value of the file is
almost entirely in the refusal line — the one that says *what came back* — so that is what these
assert hardest.
"""

from __future__ import annotations

import logging

import pytest

from acervo.models import chain, journal
from acervo.models.catalogue import load_catalogue
from acervo.models.errors import ChainExhausted, ProviderUnavailable
from acervo.models.results import Answer, TextResult

SHIPPED = load_catalogue()


@pytest.fixture
def written(monkeypatch, caplog):
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy-not-a-real-key-000")
    caplog.set_level(logging.INFO, logger=journal.LOGGER)
    return caplog


def answer() -> TextResult:
    return TextResult(text="{}", parsed={},
                      answer=Answer(provider_id="gemini-free", model="m", seconds=0.1, cost_usd=None))


def test_a_pair_that_answered_is_recorded_with_its_name_and_its_cost_in_time(written):
    chain.walk("text", [("gemini-free", "gemini/gemini-3.1-flash-lite")], SHIPPED,
               lambda candidate: answer(), chain.stamped, caller="brief")
    line = written.text
    assert "brief" in line and "gemini-free" in line and "ok in" in line


def test_a_refusal_records_why_the_next_pair_is_being_asked(written):
    """The line that would have ended the hunt in one reading rather than two deployments."""
    def ask(candidate):
        raise ProviderUnavailable(
            "unusable", "empty brief for sense s1 — got {\"senses\":[{\"senseId\":\"s1\"}]}",
            provider_id=candidate.row.id, model=candidate.model,
        )

    with pytest.raises(ChainExhausted):
        chain.walk("text", [("gemini-free", "gemini/gemini-3.1-flash-lite")], SHIPPED,
                   ask, chain.stamped, caller="brief")
    assert "unusable" in written.text
    assert "senseId" in written.text          # what actually came back
    assert "exhausted after 1 attempt" in written.text


def test_a_key_a_provider_echoed_back_never_reaches_the_log(written):
    """`ProviderError` redacts its detail at construction, and this leans on that rather than
    repeating it — a message cleaned only on its way to a log has a path that skips the cleaning."""
    def ask(candidate):
        raise ProviderUnavailable(
            "refused", "rejected key AIzaSy-not-a-real-key-000",
            provider_id=candidate.row.id, model=candidate.model,
        )

    with pytest.raises(ChainExhausted):
        chain.walk("text", [("gemini-free", "gemini/gemini-3.1-flash-lite")], SHIPPED,
                   ask, chain.stamped, caller="brief")
    assert "AIzaSy" not in written.text
    assert "«redacted»" in written.text


def test_an_excerpt_is_bounded_and_single_line():
    assert journal.excerpt("a\n  b\tc") == "a b c"
    long = journal.excerpt("x" * (journal.EXCERPT + 50))
    assert len(long) == journal.EXCERPT + 1 and long.endswith("…")


# ── the binding: where the lines actually land ──────────────────────────────


def test_the_file_is_opened_once_and_creates_its_directory(tmp_path, monkeypatch):
    """Idempotent because `create_app` runs more than once in a suite, and a second handler on the
    same logger writes every line twice — which reads as a retry that never happened."""
    from acervo.services.models import open_call_log
    from acervo.settings import Settings

    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy-not-a-real-key-000")
    path = tmp_path / "nested" / "model-calls.log"
    settings = Settings(ACERVO_CALL_LOG_PATH=str(path))
    logger = logging.getLogger(journal.LOGGER)
    before = list(logger.handlers)
    try:
        open_call_log(settings)
        open_call_log(settings)
        assert sum(getattr(h, "acervo_log_file", False) for h in logger.handlers) == 1

        journal.passed("brief", "gemini-free", "m", "unusable",
                       'got {"senses":[{"senseId":"s1"}]} AIzaSy-not-a-real-key-000', 1.5)
        for handler in logger.handlers:
            handler.flush()
        written = path.read_text(encoding="utf-8")
    finally:
        for handler in list(logger.handlers):
            if handler not in before:
                handler.close()
                logger.removeHandler(handler)

    assert "brief gemini-free:m unusable after 1.50s" in written
    assert "senseId" in written


def test_no_path_means_no_file_and_no_complaint(tmp_path):
    """A laptop run wants the lines emitted and nobody listening. Not an error, not a warning."""
    from acervo.services.models import open_call_log
    from acervo.settings import Settings

    logger = logging.getLogger(journal.LOGGER)
    before = list(logger.handlers)
    open_call_log(Settings(ACERVO_CALL_LOG_PATH=""))
    assert list(logger.handlers) == before


def test_a_call_somebody_is_waiting_on_gives_up_long_before_capture_would():
    """The bound that turned one hung connection into two minutes of "Writing a brief…".

    `TIMEOUT_SECONDS` is right for capture, which writes a whole article. The brief writer and the
    clip selector inherited it and answer in seconds — so on a real deployment a single connection
    that never opened cost the full 120 s, and the brief behind it in the queue took 1.97 s once the
    chain fell through. Asserted against the call sites rather than the constant alone, because the
    constant existing is not the fix.
    """
    from acervo.models import call
    from acervo.clips import select
    from acervo.images import brief

    assert call.SHORT_TIMEOUT_SECONDS < call.TIMEOUT_SECONDS
    for module in (brief, select):
        source = __import__("inspect").getsource(module)
        assert "timeout=call.SHORT_TIMEOUT_SECONDS" in source, module.__name__


# ── reading the log back ────────────────────────────────────────────────────


LIVE = """2026-09-12 20:32:56,709 INFO text gemini-free:gemini/gemini-3.1-flash-lite ok in 6.65s
2026-09-12 20:33:06,691 INFO brief gemini-free:gemini/gemini-3.1-flash-lite ok in 1.46s
2026-09-12 20:33:58,074 INFO brief gemini-free:gemini/gemini-3.1-flash-lite ok in 2.19s
2026-09-12 20:34:56,116 INFO brief gemini-free:gemini/gemini-3.1-flash-lite ok in 2.29s
2026-09-12 20:46:02,888 WARNING clips gemini-free:gemini/gemini-3.1-flash-lite unreachable — Timeout
2026-09-12 20:46:04,329 INFO clips gemini-free:gemini/gemini-3.5-flash-lite ok in 1.44s
2026-09-12 20:46:06,457 ERROR brief exhausted after 1 attempt(s): unusable""".splitlines()


def test_the_log_answers_how_long_each_job_takes():
    """The whole reason the reader sits beside the writer: a timeout is only defensible if the
    durations it is set from can be produced on demand."""
    from acervo.models import journal

    rows = {(row.caller, row.pair.split(":", 1)[1]): row for row in journal.summarise(LIVE)}
    brief = rows[("brief", "gemini/gemini-3.1-flash-lite")]
    assert (brief.answered, brief.failed) == (3, 0)
    assert brief.at(.5) == 2.19
    assert brief.at(1.0) == 2.29

    # A timeout is counted and contributes no duration: it took exactly as long as the bound
    # allowed, so averaging it in would measure the bound rather than the provider.
    timed_out = rows[("clips", "gemini/gemini-3.1-flash-lite")]
    assert (timed_out.answered, timed_out.failed) == (0, 1)
    assert timed_out.at(1.0) == 0.0

    # The `exhausted` line names no pair and is not a call; it must not become one.
    assert not any(row.pair.startswith("exhausted") for row in journal.summarise(LIVE))


def test_the_bounds_are_the_ones_the_measurements_support():
    """Set from `admin calls` against a real deployment, where the slowest answer of any kind was
    6.74s and the slowest brief 2.29s. Being wrong on the short side is cheap and announces itself:
    the chain asks the next pair and the log records the timeout with the job named."""
    from acervo.models import call

    slowest_seen = 6.74
    assert call.SHORT_TIMEOUT_SECONDS < call.TIMEOUT_SECONDS
    assert call.TIMEOUT_SECONDS >= slowest_seen * 4
    assert call.SHORT_TIMEOUT_SECONDS >= 2.29 * 4


def test_the_log_totals_what_failures_cost_the_person_waiting():
    """A 503 back in half a second and a timeout at the bound share a reason code and nothing else."""
    from acervo.models import journal

    lines = [
        "2026-09-15 15:12:47,476 WARNING resolve gemini-free:m unreachable after 30.01s — Timeout",
        "2026-09-15 15:13:00,349 WARNING resolve gemini-free:m unavailable after 0.40s — 503",
        "2026-09-15 15:13:02,328 INFO resolve gemini-free:m ok in 1.98s",
        "2026-09-15 15:13:03,000 INFO resolve gemini-free:m late ok after 9.00s",
    ]
    (row,) = journal.summarise(lines)
    assert (row.answered, row.failed) == (1, 2)
    assert row.lost == pytest.approx(30.41)
    assert row.at(1.0) == 1.98


def test_a_raced_chain_names_its_failures_with_their_cost(written):
    def ask(candidate):
        raise ProviderUnavailable("unavailable", "503 high demand",
                                  provider_id=candidate.row.id, model=candidate.model)

    with pytest.raises(ChainExhausted):
        chain.walk("text", [("gemini-free", "gemini/gemini-3.1-flash-lite")], SHIPPED,
                   ask, chain.stamped, caller="compose", hedge_after=5)
    assert "compose gemini-free:gemini/gemini-3.1-flash-lite unavailable after" in written.text


def test_an_outcome_line_is_key_value_quoted_where_it_must_be_and_invisible_to_the_timings(written):
    """A pronunciation says what it did with its answer on a line of its own. The timings reader
    must read straight past it, or every clip would count as a pair nobody can name."""
    journal.answered("pronounce-word", "google-tts", "wavenet", 0.41)
    journal.outcome("pronounce-word", target="lexeme:abc", text='say "picar" = bite', chars=5,
                    voice=None, seconds=0.5, result="stored")
    journal.outcome("pronounce-word", True, result="refused:llm_rate_limited")
    lines = [record.getMessage() for record in written.records]
    assert lines[1] == 'pronounce-word outcome target=lexeme:abc text="say \\"picar\\" = bite" chars=5 seconds=0.50 result=stored'
    assert written.records[2].levelno == logging.WARNING

    stamped = [f"2026-09-15 10:00:00,000 {record.levelname} {record.getMessage()}" for record in written.records]
    timings = journal.summarise(stamped)
    assert [(one.caller, one.pair, one.answered, one.failed) for one in timings] == [
        ("pronounce-word", "google-tts:wavenet", 1, 0)
    ]

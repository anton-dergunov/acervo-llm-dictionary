"""The request id, the shared log opener, the activity log and its reader.

What is pinned here is what breaks quietly: an id that leaks from one job to the next, a stranger's
header written into a log, a second handler doubling every line, and a stamp that would stop
`admin calls` from reading its own file.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from acervo import activity, logfiles, trace
from acervo.models import journal


@pytest.fixture
def opened():
    """Handlers a test opened are closed and removed again: the loggers are the process's."""
    names: list[str] = []
    yield names.append
    for name in names:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            if getattr(handler, "acervo_log_file", False):
                handler.close()
                logger.removeHandler(handler)
        logger.propagate = True


def flush(name: str) -> None:
    for handler in logging.getLogger(name).handlers:
        handler.flush()


# ── the id ──────────────────────────────────────────────────────────────────


def test_an_id_has_the_shape_of_every_other_id():
    assert trace.well_formed(trace.mint())
    assert len(trace.mint()) == 15


@pytest.mark.parametrize("stranger", ["", "short", "UPPERCASE000001", "a b c d e f g h", None, 7,
                                      "abcdefghij12345\nINFO forged line"])
def test_a_strangers_header_is_not_taken_up(stranger):
    """It is about to be written into a log, so it is this shape or it is ignored."""
    with trace.scope("jobjobjobjob001"):
        assert trace.adopt(stranger) == "jobjobjobjob001"
        assert trace.well_formed(trace.begin(stranger))
        assert trace.current() != stranger


def test_a_well_formed_id_is_kept_so_the_caller_stays_one_piece_of_work():
    with trace.scope(""):
        assert trace.begin("abcdefghij12345") == "abcdefghij12345"
        assert trace.current() == "abcdefghij12345"


def test_one_jobs_id_does_not_outlive_the_job():
    """The runner takes one job after another on one thread."""
    with trace.scope(""):
        with trace.scope("jobjobjobjob001"):
            assert trace.current() == "jobjobjobjob001"
        assert trace.current() == ""


# ── opening a log ───────────────────────────────────────────────────────────


def test_a_log_is_opened_once_and_its_lines_carry_the_id(tmp_path, opened):
    opened("acervo.test.stamped")
    path = tmp_path / "nested" / "one.log"
    logfiles.open_rotating("acervo.test.stamped", path, 10_000, 1)
    logfiles.open_rotating("acervo.test.stamped", path, 10_000, 1)
    logger = logging.getLogger("acervo.test.stamped")
    assert len(logger.handlers) == 1

    with trace.scope("jobjobjobjob001"):
        logger.info("inside")
    with trace.scope(""):
        logger.info("outside")
    flush("acervo.test.stamped")
    inside, outside = path.read_text(encoding="utf-8").splitlines()
    assert inside.endswith("inside rid=jobjobjobjob001")
    assert outside.endswith("outside")


def test_a_log_that_names_its_own_id_is_left_unstamped(tmp_path, opened):
    opened("acervo.test.plain")
    path = tmp_path / "plain.log"
    logfiles.open_rotating("acervo.test.plain", path, 10_000, 1, stamp=False)
    with trace.scope("jobjobjobjob001"):
        logging.getLogger("acervo.test.plain").info("job end id=jobjobjobjob001")
    flush("acervo.test.plain")
    assert "rid=" not in path.read_text(encoding="utf-8")


def test_a_log_that_cannot_be_opened_says_so_to_its_caller(tmp_path, opened):
    opened("acervo.test.unwritable")
    blocked = tmp_path / "a-file"
    blocked.write_text("not a directory")
    with pytest.raises(OSError):
        logfiles.open_rotating("acervo.test.unwritable", blocked / "one.log", 10_000, 1)
    assert not logging.getLogger("acervo.test.unwritable").handlers


def test_the_stamp_does_not_stop_the_call_log_being_read_back(tmp_path, opened):
    """`admin calls` reads this file with two patterns written before the stamp existed."""
    opened(journal.LOGGER)
    path = tmp_path / "model-calls.log"
    logfiles.open_rotating(journal.LOGGER, path, 100_000, 1)
    with trace.scope("jobjobjobjob001"):
        journal.answered("brief", "gemini-free", "m", 2.0)
        journal.passed("brief", "gemini-free", "m", "timeout", "gave up", 30.0)
        journal.outcome("brief", result="stored")
    flush(journal.LOGGER)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert all(line.endswith("rid=jobjobjobjob001") for line in lines)
    (row,) = journal.summarise(lines)
    assert (row.answered, row.failed, row.at(1.0), row.lost) == (1, 1, 2.0, 30.0)


# ── the activity log ────────────────────────────────────────────────────────


def test_a_line_is_pairs_a_grep_can_answer(caplog):
    with caplog.at_level(logging.INFO, logger=activity.LOGGER):
        activity.note("media removed", ref="images/es/a b.webp", reason="replaced", empty="",
                      absent=None, seconds=1.5)
    assert caplog.messages == ['media removed ref="images/es/a b.webp" reason=replaced seconds=1.50']


def test_a_refusal_keeps_the_sentence_and_its_level_says_whose_fault(caplog):
    with caplog.at_level(logging.INFO, logger=activity.LOGGER):
        activity.refused(409, "stale_record", "This entry was changed somewhere else.", id="abc")
        activity.refused(500, "server_error", "KeyError: 'x'")
    asked, crashed = caplog.records
    assert asked.levelname == "WARNING" and crashed.levelname == "ERROR"
    assert asked.getMessage() == (
        'refused status=409 code=stale_record id=abc message="This entry was changed somewhere else."')


def test_a_long_message_cannot_fill_the_file():
    assert len(activity.fields({"message": "word " * 1000})) < activity.EXCERPT + 20


# ── reading the three back ──────────────────────────────────────────────────


def three_logs(tmp_path):
    calls, jobs, acts = (tmp_path / name for name in ("calls.log", "jobs.log", "activity.log"))
    (tmp_path / "calls.log.1").write_text(
        "2026-10-05 09:00:00,000 INFO enrich gemini:m ok in 1.00s rid=jobold000000001\n")
    calls.write_text(
        "2026-10-05 10:00:02,000 INFO speak gemini:tts ok in 2.00s rid=jobjobjobjob001\n"
        "2026-10-05 10:00:05,000 WARNING speak gemini:tts timeout after 30.00s — gave up\n"
        "and said so on a second line rid=jobjobjobjob001\n")
    jobs.write_text(
        "2026-10-05 10:00:01,000 INFO job start id=jobjobjobjob001 kind=loop\n"
        "2026-10-05 10:00:09,000 WARNING job step id=jobjobjobjob001 step=loop.render "
        "state=failed operationId=op-77\n")
    acts.write_text(
        "2026-10-05 10:00:03,000 WARNING refused status=409 code=stale_record rid=reqreqreqreq001\n")
    return {"call": calls, "job": jobs, "act": acts, "absent": tmp_path / "none.log", "off": None}


def test_the_three_logs_read_as_one_account_in_the_order_it_happened(tmp_path):
    found = activity.entries(three_logs(tmp_path))
    assert [(when[11:19], source) for when, _, source, _ in found] == [
        ("09:00:00", "call"), ("10:00:01", "job"), ("10:00:02", "call"), ("10:00:03", "act"),
        ("10:00:05", "call"), ("10:00:09", "job"),
    ]
    # A message that kept its own line break stays with the entry it belongs to.
    assert found[4][3].endswith("gave up and said so on a second line rid=jobjobjobjob001")


def test_an_id_finds_the_job_and_everything_done_on_its_behalf(tmp_path):
    found = activity.entries(three_logs(tmp_path))
    about = activity.select(found, identifier="jobjobjobjob001")
    assert [source for _, _, source, _ in about] == ["job", "call", "call", "job"]
    # The generator's own id, read off its container's log, leads back to the job.
    assert [source for _, _, source, _ in activity.select(found, identifier="op-77")] == ["job"]
    # Not a substring match: another job's id is another job.
    assert activity.select(found, identifier="jobjobjobjob00") == []


def test_failed_keeps_only_what_went_wrong(tmp_path):
    wrong = activity.select(activity.entries(three_logs(tmp_path)), failed=True)
    assert [source for _, _, source, _ in wrong] == ["act", "call", "job"]


def test_admin_log_prints_them_and_says_when_there_is_nothing(tmp_path, capsys):
    from types import SimpleNamespace

    from acervo.admin import show_log

    logs = three_logs(tmp_path)
    settings = SimpleNamespace(call_log_path=logs["call"], job_log_path=logs["job"],
                               activity_log_path=logs["act"])
    assert show_log(settings, "jobjobjobjob001", False, 60) == 0
    printed = capsys.readouterr().out.splitlines()
    assert len(printed) == 4
    assert printed[0].startswith("2026-10-05 10:00:01,000 job  INFO    job start")
    assert show_log(settings, "", True, 1) == 0
    assert "step=loop.render" in capsys.readouterr().out
    assert show_log(settings, "nobodynobody001", False, 60) == 1
    assert "Nothing filed under nobodynobody001" in capsys.readouterr().out


# ── the companions are told whose work it is ────────────────────────────────


class Recorder:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.headers: list[dict] = []

    def request(self, method, url, **kwargs):
        self.headers.append(dict(kwargs.get("headers") or {}))
        return httpx.Response(200, json=self.payload)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def test_the_loop_generator_is_sent_the_id_on_every_request():
    from acervo.loops.client import LoopService

    http = Recorder({"status": "ok"})
    service = LoopService("http://lexibeat/api/v1", http=http, request_id="jobjobjobjob001")
    service.alive()
    service.track("/api/v1/loops/op/audio")
    assert [sent.get("X-Request-ID") for sent in http.headers] == ["jobjobjobjob001"] * 2


def test_the_corpus_is_sent_the_id_beside_the_operators_token():
    from acervo.clips.corpus import Corpus

    http = Recorder({"operation_id": "op-1", "status": "running"})
    corpus = Corpus("http://speech", http=http, operator_token="operator", request_id="jobjobjobjob001")
    corpus.operation("op-1")
    assert http.headers == [{"Authorization": "Bearer operator", "X-Request-ID": "jobjobjobjob001"}]


def test_a_caller_with_no_id_sends_no_header():
    from acervo.loops.client import LoopService

    http = Recorder({"status": "ok"})
    LoopService("http://lexibeat/api/v1", http=http).alive()
    assert "X-Request-ID" not in http.headers[0]

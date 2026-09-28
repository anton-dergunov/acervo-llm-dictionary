"""What a long Anki run says while it works: stage lines on stderr, a count at most every few seconds."""

import io

import pytest

from acervo.consumers.anki.progress import Progress
from acervo.consumers.anki.robot import AnkiRobot


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_count_is_said_at_the_start_every_few_seconds_and_at_the_end():
    clock, said = Clock(), io.StringIO()
    counter = Progress(said, clock=clock, every=5).count("Shrinking pictures", 4)
    counter.step()            # too soon to say
    clock.now = 6
    counter.step()            # 2 of 4 in six seconds: six more to go
    counter.step()
    clock.now = 7
    counter.step()            # the end is always said
    assert said.getvalue().splitlines() == [
        "[0s] Shrinking pictures: 0/4",
        "[6s] Shrinking pictures: 2/4, about 6s left",
        "[7s] Shrinking pictures: 4/4",
    ]


class Media:
    """Anki's media sync status, one reading per call."""

    def __init__(self, readings):
        self.readings = list(readings)
        self.aborted = False

    def media_sync_status(self):
        active, checked = self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]
        progress = type("Progress", (), {"checked": checked, "added": "", "removed": ""})
        return type("Status", (), {"active": active, "progress": progress})

    def abort_media_sync(self):
        self.aborted = True


def robot_waiting(stall: float, said: io.StringIO) -> AnkiRobot:
    robot = AnkiRobot.__new__(AnkiRobot)
    robot.settings = type("Settings", (), {"media_timeout_seconds": stall})
    robot.progress = Progress(said, every=0)
    return robot


def test_media_sync_may_run_longer_than_the_stall_bound_while_it_moves(monkeypatch):
    moments = iter(range(100))
    monkeypatch.setattr("acervo.consumers.anki.robot.time.monotonic", lambda: float(next(moments)))
    monkeypatch.setattr("acervo.consumers.anki.robot.time.sleep", lambda _: None)
    said = io.StringIO()
    readings = [(True, f"Checked: {n}") for n in range(10)] + [(False, "")]

    robot_waiting(3, said)._wait_for_media(Media(readings))

    assert "Media sync: Checked: 9" in said.getvalue()
    assert said.getvalue().splitlines()[-1].endswith("Media sync finished")


def test_media_sync_that_stops_moving_is_abandoned_saying_where_it_stopped(monkeypatch):
    moments = iter(range(100))
    monkeypatch.setattr("acervo.consumers.anki.robot.time.monotonic", lambda: float(next(moments)))
    monkeypatch.setattr("acervo.consumers.anki.robot.time.sleep", lambda _: None)
    media = Media([(True, "Checked: 1"), (True, "Checked: 2")])

    with pytest.raises(TimeoutError, match=r"no progress for 3 seconds \(last: Checked: 2\)"):
        robot_waiting(3, io.StringIO())._wait_for_media(media)
    assert media.aborted

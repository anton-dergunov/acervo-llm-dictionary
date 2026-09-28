"""What a long Anki run is doing, as plain lines on stderr.

A first push shrinks thousands of pictures and uploads them, which takes minutes, and without this
the only output is the JSON result at the end. stdout carries that result, so progress goes to
stderr. It is a line at a time rather than a redrawn bar: the worker runs under `docker compose run`
behind ssh with no terminal, where a bar arrives as one long line of carriage returns.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import TextIO


def _clock(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}m{seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


class Progress:
    """Stage lines, each stamped with the time since the run began."""

    def __init__(self, stream: TextIO | None = None, *, clock: Callable[[], float] = time.monotonic,
                 every: float = 5.0):
        self.stream = stream
        self.clock = clock
        self.every = every
        self.started = clock()

    def say(self, message: str) -> None:
        stream = self.stream if self.stream is not None else sys.stderr
        print(f"[{_clock(self.clock() - self.started)}] {message}", file=stream, flush=True)

    def count(self, what: str, total: int) -> Counter:
        return Counter(self, what, total)


class Counter:
    """`what: done/total`, said at most every few seconds and always once at the end."""

    def __init__(self, progress: Progress, what: str, total: int):
        self.progress = progress
        self.what = what
        self.total = total
        self.done = 0
        self.began = progress.clock()
        self.last = self.began
        if total:
            progress.say(f"{what}: 0/{total}")

    def step(self, amount: int = 1) -> None:
        self.done += amount
        now = self.progress.clock()
        if self.done < self.total and now - self.last < self.progress.every:
            return
        self.last = now
        line = f"{self.what}: {self.done}/{self.total}"
        if self.done < self.total and self.done:
            left = (now - self.began) / self.done * (self.total - self.done)
            line += f", about {_clock(left)} left"
        self.progress.say(line)

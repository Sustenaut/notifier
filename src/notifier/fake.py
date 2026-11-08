"""`notifier fake-sender`: senders that exist only to be watched.

Each fake sender writes what every real sender writes: through the integrations
library's StorageSink, one file per cycle to the notifier's call log buffer
(storage's `calls-notifier`), whose metadata is the sender's report. So the ingest
pod loads it into `calls_notifier.status`, and observability sees a sender like any
other. Nothing else is touched.

- **One sender**, `e2e`, run every two minutes by the CronJob `fake-sender`, is the
  steady one: observability expects it always on, so pausing the CronJob makes
  `sender_silent` open for `notifier/e2e`, and resuming it ends the signal.
  `k8s/admin/e2e.sh` does that, and checks the notifier posts each once.
- **Many**, for load: `--senders N` writes N senders' reports (`e2e-a`, `e2e-b`, ...),
  each with `--calls` made-up calls to the plugin `e2e.fake`, and `--minutes`
  repeats it every two minutes. Observability doesn't expect them, so they never make
  a signal when they stop.
"""

from __future__ import annotations

import random
import string
import time
from datetime import datetime, timezone
from typing import Callable, Protocol

from integrations.calls import CallRecord

STEADY = "e2e"
PLUGIN = "e2e.fake"
EVERY_SECONDS = 120


class Sink(Protocol):
    def write(self, record: CallRecord) -> None: ...

    def flush(self) -> None: ...


def names(senders: int) -> list[str]:
    """The steady sender alone for one; for more, e2e-a ... e2e-z, then e2e-aa ...:
    letters only, so observability never reads them as a pod's generated suffix."""
    if senders < 1:
        raise ValueError("--senders is at least 1")
    if senders == 1:
        return [STEADY]
    out, letters, width = [], string.ascii_lowercase, 1
    while len(out) < senders:
        for n in range(len(letters) ** width):
            suffix = "".join(letters[(n // len(letters) ** i) % len(letters)] for i in reversed(range(width)))
            out.append(f"{STEADY}-{suffix}")
            if len(out) == senders:
                break
        width += 1
    return out


def call(repo: str, now: datetime, n: int, latency: Callable[[], int]) -> CallRecord:
    return CallRecord(at=now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), repo=repo, app="fake-sender",
                      plugin=PLUGIN, operation="call", request_id=f"fake-{now.timestamp():.0f}-{n}",
                      latency_ms=latency(), status=200, outcome="ok", retries=0, bytes_in=0, bytes_out=0,
                      mode="advisory", route="none")


def report(sinks: dict[str, Sink], repo: str, calls: int, now: datetime,
           latency: Callable[[], int] = lambda: random.randint(20, 400)) -> int:  # noqa: S311 - not for secrets
    """One cycle: each sender's calls, then its report. Returns the calls written."""
    for sink in sinks.values():
        for n in range(calls):
            sink.write(call(repo, now, n, latency))
        sink.flush()
    return calls * len(sinks)


def run(make_sink: Callable[[str], Sink], repo: str, senders: int, calls: int, minutes: int,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep: Callable[[float], None] = time.sleep) -> list[str]:
    """Every sender's report now, and again every two minutes until `minutes` have
    passed (once, with no minutes). Returns a line for each cycle."""
    sinks = {name: make_sink(name) for name in names(senders)}
    cycles = max(1, minutes * 60 // EVERY_SECONDS)
    lines = []
    for cycle in range(cycles):
        if cycle:
            sleep(EVERY_SECONDS)
        written = report(sinks, repo, calls, clock())
        lines.append(f"reported {len(sinks)} sender{'s' if len(sinks) != 1 else ''}, {written} calls")
    return lines

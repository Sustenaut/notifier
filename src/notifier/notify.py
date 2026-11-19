"""One run: read the signals written in the last day from observability.signals, post
each one's start and end once, and remember what was posted.

A signal is written twice, when it starts and when it ends, both with the same
`started_at`, so a rule, a subject and that moment name it. Each is posted when it
opens and again when it ends; one that opened and ended between two runs is posted
once, as both. The first run, with nothing remembered, posts none of what it finds:
it remembers it all, and says it has started.

Signals of one rule going to one channel as the same kind of post (open, ended, or
both) in one run are one post when there are two or more: one fault seen from many
subjects is one message, not a flood. A post that fails is remembered for none of
its signals, so the next run tries them all again.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from notifier import messages
from notifier.routes import Routes
from notifier.state import Posted, Store, key

SIGNALS = """\
SELECT rule_id, rule_version, subject, severity, started_at, ended_at, TO_JSON_STRING(evidence) AS evidence
FROM observability.signals
WHERE started_at >= TIMESTAMP_SUB({{now}}, INTERVAL 30 DAY)
  AND emitted_at >= TIMESTAMP_SUB({{now}}, INTERVAL 1 DAY)
"""


def timestamp(moment: datetime) -> str:
    """A BigQuery TIMESTAMP literal, in UTC."""
    return f"TIMESTAMP '{moment.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}+00:00'"


def utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@dataclass
class Signal:
    rule_id: str
    rule_version: str
    subject: str
    severity: str
    started_at: datetime
    ended_at: datetime | None
    evidence: dict[str, Any]

    @property
    def key(self) -> str:
        return key(self.rule_id, self.subject, self.started_at)


def signals(rows: list[dict[str, Any]]) -> list[Signal]:
    """Each signal once, ended if its end has been written."""
    found: dict[tuple, Signal] = {}
    for row in rows:
        started = utc(row["started_at"])
        ended = utc(row["ended_at"]) if row.get("ended_at") is not None else None
        evidence = json.loads(row["evidence"]) if isinstance(row["evidence"], str) else dict(row["evidence"] or {})
        signal = Signal(row["rule_id"], str(row["rule_version"]), row["subject"], row["severity"], started, ended,
                        evidence)
        known = found.get((signal.rule_id, signal.subject, started))
        if known is None or (ended is not None and known.ended_at is None):
            found[(signal.rule_id, signal.subject, started)] = signal
    return sorted(found.values(), key=lambda s: (s.started_at, s.rule_id, s.subject))


@dataclass
class Outcome:
    posted: list[tuple[str, str]] = field(default_factory=list)  # channel, text
    failed: list[str] = field(default_factory=list)  # why each post failed
    seeded: bool = False
    saved: bool = False


def run(query: Callable[[str], list[dict[str, Any]]], post: Callable[[str, str], None], store: Store,
        routes: Routes, now: datetime, link: Callable[[Signal], str]) -> Outcome:
    """One run. `post` raises when Slack refuses or doesn't answer; `link` is a signal's page."""
    out = Outcome()
    posted, read = store.load()
    found = signals(query(SIGNALS.replace("{{now}}", timestamp(now))))
    if posted is None:
        posted = Posted(started=now.isoformat())
        for signal in found:
            posted.mark(signal.key, "open", now)
            if signal.ended_at is not None:
                posted.mark(signal.key, "ended", now)
        out.seeded = True
        if routes.default is not None:
            text = messages.started(sum(1 for s in found if s.ended_at is None))
            try:
                post(routes.default.channel, text)
                out.posted.append((routes.default.channel, text))
            except Exception as error:  # noqa: BLE001 - the integrations client's refusal or failure
                out.failed.append(f"the first message: {error}")
        store.save(posted, read)
        out.saved = True
        return out
    changed = False
    groups: dict[tuple[str, str, str], list[Signal]] = {}  # rule, channel, what: in the order found
    for signal in found:
        opened, ended = posted.has(signal.key, "open"), posted.has(signal.key, "ended")
        if signal.ended_at is None and opened or signal.ended_at is not None and ended:
            continue
        what = "open" if signal.ended_at is None else ("ended" if opened else "both")
        channel = routes.channel_for(signal.rule_id, signal.subject, signal.severity)
        if channel is not None:
            groups.setdefault((signal.rule_id, channel, what), []).append(signal)
            continue
        # A signal no route posts is remembered too, so a route added later doesn't
        # post what happened before it.
        mark(posted, signal, what, now)
        changed = True
    for (rule_id, channel, what), group in groups.items():
        if len(group) == 1:
            text = messages.text(group[0], what, link(group[0]))
        else:
            text = messages.grouped(group, what, [link(signal) for signal in group])
        try:
            post(channel, text)
        except Exception as error:  # noqa: BLE001 - the integrations client's refusal or failure
            # Not remembered, so the next run tries them all again.
            named = group[0].subject if len(group) == 1 else f"{len(group)} subjects"
            out.failed.append(f"{rule_id} {named}: {error}")
            continue
        out.posted.append((channel, text))
        for signal in group:
            mark(posted, signal, what, now)
        changed = True
    before = len(posted.signals)
    posted.prune(now)
    if changed or len(posted.signals) != before:
        store.save(posted, read)
        out.saved = True
    return out


def mark(posted: Posted, signal: Signal, what: str, now: datetime) -> None:
    """Remember what was posted for the signal: both its start and its end, for "both"."""
    for done in (("open", "ended") if what == "both" else (what,)):
        posted.mark(signal.key, done, now)

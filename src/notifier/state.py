"""Which signals have been posted: a small JSON file in storage's `notifier` tenant,
named by the head `posted`.

A file there never changes, so each run that posts something uploads a new one and
moves the head to it, with If-Match on the hash it read. Two runs can't both move
it, and the CronJob runs one at a time anyway. Posting comes before the move, so a
run that dies between the two posts its messages again next time: a signal may be
posted twice, never left out.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

TENANT = "notifier"
HEAD = "posted"
# How long a signal that has ended is remembered, and how long one at all.
KEEP_ENDED = timedelta(days=7)
KEEP_ANY = timedelta(days=30)


def key(rule_id: str, subject: str, started_at: datetime) -> str:
    return json.dumps([rule_id, subject, started_at.isoformat()])


@dataclass
class Posted:
    """Each signal's key, and what has been posted for it: "open" when its start was,
    "ended" when its end was (or both together), with when."""

    signals: dict[str, dict[str, str]] = field(default_factory=dict)
    started: str = ""  # when the first run seeded it

    def has(self, signal_key: str, what: str) -> bool:
        return what in self.signals.get(signal_key, {})

    def mark(self, signal_key: str, what: str, at: datetime) -> None:
        self.signals.setdefault(signal_key, {})[what] = at.isoformat()

    def prune(self, now: datetime) -> None:
        def kept(signal_key: str, done: dict[str, str]) -> bool:
            started = datetime.fromisoformat(json.loads(signal_key)[2])
            if now - started > KEEP_ANY:
                return False
            return "ended" not in done or now - datetime.fromisoformat(done["ended"]) <= KEEP_ENDED

        self.signals = {k: v for k, v in self.signals.items() if kept(k, v)}

    def encode(self) -> bytes:
        return json.dumps({"started": self.started, "signals": self.signals}, sort_keys=True, indent=1).encode()

    @classmethod
    def decode(cls, data: bytes) -> Posted:
        found = json.loads(data)
        return cls(signals=dict(found.get("signals", {})), started=str(found.get("started", "")))


class Store(Protocol):
    def load(self) -> tuple[Posted | None, str | None]: ...

    def save(self, posted: Posted, read: str | None) -> None: ...


class StorageStore:
    """The state in storage, through the integrations library's client."""

    def __init__(self, storage) -> None:  # noqa: ANN001 - integrations.clients.storage.Storage
        self.storage = storage

    def load(self) -> tuple[Posted | None, str | None]:
        from integrations.clients.storage import NotFound  # noqa: PLC0415

        try:
            data, etag = self.storage.get_head(HEAD)
        except NotFound:
            return None, None
        return Posted.decode(data), etag

    def save(self, posted: Posted, read: str | None) -> None:
        stored = self.storage.upload_file(posted.encode(), name="posted.json")
        self.storage.move_head(HEAD, stored["id"], if_match=read)

"""Steps for the state in storage, through a stand-in for the integrations library's
storage client: its heads and files in memory."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest
from integrations.clients.storage import NotFound
from pytest_bdd import given, parsers, scenarios, then, when

from notifier.state import Posted, StorageStore, key

scenarios("../features/state.feature")

NOW = datetime(2026, 11, 1, 10, 30, tzinfo=timezone.utc)


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.heads: dict[str, str] = {}
        self.moves: list[tuple[str, str, str | None]] = []

    def get_head(self, name: str) -> tuple[bytes, str | None]:
        if name not in self.heads:
            raise NotFound("getHead", 404, "no such head")
        return self.files[self.heads[name]], self.heads[name]

    def upload_file(self, data: bytes, *, name: str) -> dict:
        digest = hashlib.sha256(data).hexdigest()
        self.files[digest] = data
        return {"id": digest, "name": name}

    def move_head(self, name: str, hash: str, *, if_match: str | None = None) -> dict:  # noqa: A002
        self.moves.append((name, hash, if_match))
        self.heads[name] = hash
        return {"hash": hash}


def remembering(listed: str) -> Posted:
    rule, subject = listed.split()
    posted = Posted(started=NOW.isoformat())
    posted.mark(key(rule, subject, NOW), "open", NOW)
    return posted


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def loaded() -> dict:
    return {}


@given(parsers.parse('storage has no head "{name}"'))
def no_head(storage: FakeStorage, name: str) -> None:
    assert name not in storage.heads


@given(parsers.parse('storage\'s head "{name}" names a state remembering "{listed}"'))
def head_names(storage: FakeStorage, name: str, listed: str) -> None:
    storage.move_head(name, storage.upload_file(remembering(listed).encode(), name="posted.json")["id"])
    storage.moves.clear()


@when("the state is loaded")
def load(storage: FakeStorage, loaded: dict) -> None:
    loaded["posted"], loaded["read"] = StorageStore(storage).load()


@then("there is no state")
def none(loaded: dict) -> None:
    assert loaded["posted"] is None and loaded["read"] is None


@then(parsers.parse('it remembers "{listed}"'))
def remembers(loaded: dict, listed: str) -> None:
    assert [" ".join(json.loads(k)[:2]) for k in loaded["posted"].signals] == [listed]


@when(parsers.parse('a state remembering "{listed}" is saved'))
def save(storage: FakeStorage, loaded: dict, listed: str) -> None:
    StorageStore(storage).save(remembering(listed), loaded["read"])


@then(parsers.parse('the head "{name}" was moved only if it had never moved'))
def first_move(storage: FakeStorage, name: str) -> None:
    assert [(n, m) for n, _, m in storage.moves] == [(name, None)]


@then(parsers.parse('the head "{name}" was moved only if it still named what was read'))
def later_move(storage: FakeStorage, loaded: dict, name: str) -> None:
    assert [(n, m) for n, _, m in storage.moves] == [(name, loaded["read"])] and loaded["read"]


@then(parsers.parse('the head "{name}" names a file holding "{listed}"'))
def holds(storage: FakeStorage, name: str, listed: str) -> None:
    posted = Posted.decode(storage.files[storage.heads[name]])
    assert [" ".join(json.loads(k)[:2]) for k in posted.signals] == [listed]

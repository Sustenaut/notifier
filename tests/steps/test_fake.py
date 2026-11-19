"""Steps for the fake senders: fake.run with sinks in memory, and the command with
storage a fake transport that takes every file."""

from __future__ import annotations

import shlex
import sys
from datetime import datetime, timezone

import pytest
from integrations.calls import Request, Response
from pytest_bdd import parsers, scenarios, then, when

from notifier import cli, fake

scenarios("../features/fake.feature")


class MemorySink:
    def __init__(self) -> None:
        self.calls: list = []
        self.flushes = 0

    def write(self, record) -> None:  # noqa: ANN001 - a CallRecord
        self.calls.append(record)

    def flush(self) -> None:
        self.flushes += 1


class TakesEverything:
    """A transport storage answers, taking each file."""

    def __init__(self) -> None:
        self.sent: list[Request] = []

    def send(self, request: Request, timeout: float) -> Response:
        self.sent.append(request)
        return Response(200, b"{}")


@pytest.fixture
def world() -> dict:
    return {"transport": TakesEverything()}


@when(parsers.parse("{count:d} fake senders are named"))
def named(ctx, count: int) -> None:
    ctx.attempt(lambda: fake.names(count))


@when(parsers.parse("{senders:d} fake senders report {calls:d} calls each for {minutes:d} minutes"))
def report(ctx, world: dict, senders: int, calls: int, minutes: int) -> None:
    world["sinks"], world["slept"] = {}, []

    def make(name: str) -> MemorySink:
        world["sinks"][name] = MemorySink()
        return world["sinks"][name]

    ctx.attempt(lambda: fake.run(make, "notifier", senders, calls, minutes,
                                 clock=lambda: datetime(2026, 11, 8, 5, 0, tzinfo=timezone.utc),
                                 sleep=world["slept"].append))


@when(parsers.parse('the fake sender is run with "{args}"'))
def run_fake(ctx, world: dict, args: str) -> None:
    argv = ["fake-sender", *shlex.split(args)]
    ctx.attempt(lambda: sys.exit(cli.main(argv, transport=world["transport"], storage_token=lambda: "t")))


@when(parsers.parse('the link is read from "{text}"'))
def link(ctx, text: str) -> None:
    ctx.attempt(lambda: cli.link_of(text.replace("\\n", "\n")))


@then("no item of the result is there twice")
def no_item_twice(ctx) -> None:
    assert len(ctx.result) == len(set(ctx.result)), ctx.result


@then(parsers.parse('each sender wrote {calls:d} calls to "{plugin}" and reported {times:d} times'))
def wrote(world: dict, calls: int, plugin: str, times: int) -> None:
    assert world["sinks"]
    for sink in world["sinks"].values():
        assert len(sink.calls) == calls and {c.plugin for c in sink.calls} <= {plugin} and sink.flushes == times
        assert all(c.repo == "notifier" and c.outcome == "ok" and c.at == "2026-11-08T05:00:00Z" for c in sink.calls)


@then(parsers.parse("it waited {seconds:d} seconds once"))
def waited(world: dict, seconds: int) -> None:
    assert world["slept"] == ([seconds] if seconds else [])


@then(parsers.parse('storage got {count:d} files under "{prefix}"'))
def stored(world: dict, count: int, prefix: str) -> None:
    puts = [r.url for r in world["transport"].sent if r.method == "PUT"]
    assert len(puts) == count and all(prefix in url for url in puts), puts

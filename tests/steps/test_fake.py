"""Steps for the fake senders: fake.run with sinks in memory, and the command with
storage a fake transport that takes every file."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
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
    return {}


@then(parsers.parse('{count:d} senders are named "{first}" to "{last}"'))
def named(count: int, first: str, last: str) -> None:
    got = fake.names(count)
    assert (len(got), got[0], got[-1], len(set(got))) == (count, first, last, count)


@when(parsers.parse("{senders:d} fake senders report {calls:d} calls each for {minutes:d} minutes"))
def report(world: dict, senders: int, calls: int, minutes: int) -> None:
    world["sinks"], world["slept"] = {}, []

    def make(name: str) -> MemorySink:
        world["sinks"][name] = MemorySink()
        return world["sinks"][name]

    world["lines"] = fake.run(make, "notifier", senders, calls, minutes,
                              clock=lambda: datetime(2026, 11, 8, 5, 0, tzinfo=timezone.utc),
                              sleep=world["slept"].append)


@then(parsers.parse('each sender wrote {calls:d} calls to "{plugin}" and reported {times:d} times'))
def wrote(world: dict, calls: int, plugin: str, times: int) -> None:
    for sink in world["sinks"].values():
        assert len(sink.calls) == calls and {c.plugin for c in sink.calls} <= {plugin} and sink.flushes == times
        assert all(c.repo == "notifier" and c.outcome == "ok" and c.at == "2026-11-08T05:00:00Z" for c in sink.calls)


@then(parsers.parse("it waited {seconds:d} seconds once"))
def waited(world: dict, seconds: int) -> None:
    assert world["slept"] == ([seconds] if seconds else [])


@then(parsers.parse('it says "{line}" twice'))
def says_twice(world: dict, line: str) -> None:
    assert world["lines"] == [line, line]


def run_command(world: dict, args: list[str], storage: bool) -> None:
    world["transport"] = TakesEverything()
    out, err = io.StringIO(), io.StringIO()
    env = {"NOTIFIER_STORAGE_URL": "https://storage.test"} if storage else {}
    with pytest.MonkeyPatch.context() as patch, redirect_stdout(out), redirect_stderr(err):
        patch.delenv("NOTIFIER_STORAGE_URL", raising=False)
        for k, v in env.items():
            patch.setenv(k, v)
        world["code"] = cli.main(["fake-sender", *args], transport=world["transport"], storage_token=lambda: "t")
    world["out"], world["err"] = out.getvalue(), err.getvalue()


@when(parsers.re(r'I run the fake sender with (?P<args>(?:"[^"]*" ?)+)$'))
def run_fake(world: dict, args: str) -> None:
    run_command(world, args.strip().strip('"').split('" "'), True)


@when(parsers.re(r'I run the fake sender with (?P<args>(?:"[^"]*" ?)+), (?P<storage>with|without) storage$'))
def run_fake_storage(world: dict, args: str, storage: str) -> None:
    run_command(world, args.strip().strip('"').split('" "'), storage == "with")


@then(parsers.parse('it succeeds with "{line}"'))
def succeeds(world: dict, line: str) -> None:
    assert world["code"] == 0 and world["out"].splitlines() == [line], (world["out"], world["err"])


@then(parsers.parse('storage got {count:d} files under "{prefix}"'))
def stored(world: dict, count: int, prefix: str) -> None:
    puts = [r.url for r in world["transport"].sent if r.method == "PUT"]
    assert len(puts) == count and all(prefix in url for url in puts), puts


@then(parsers.parse('it fails with {code:d}, saying "{message}"'))
def fails(world: dict, code: int, message: str) -> None:
    assert world["code"] == code and message in world["err"], world["err"]


@then(parsers.parse('the link of "{text}" is "{link}"'))
def link(text: str, link: str) -> None:
    assert cli.link_of(text.replace("\\n", "\n").replace("\\|", "|")) == link


@then(parsers.re(r'the link of "(?P<text>[^"]*)" is ""$'))
def no_link(text: str) -> None:
    assert cli.link_of(text.replace("\\n", "\n")) == ""

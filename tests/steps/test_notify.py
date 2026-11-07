"""Steps for a run, with fakes for BigQuery (rows the query answers), Slack (the
integrations library's FakeSlackPost) and storage (a head in memory, moved with
If-Match)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from integrations.calls import Refused
from integrations.clients.slack import FakeSlackPost
from observability import links
from pytest_bdd import given, parsers, scenarios, then, when

from notifier import notify, routes
from notifier.state import Posted, key

scenarios("../features/notify.feature")

DAY = "2026-11-01"


def at(clock: str) -> datetime:
    return datetime.fromisoformat(f"{DAY}T{clock}:00").replace(tzinfo=timezone.utc)


class FakeStore:
    """The head `posted`, in memory: a save must name the hash it read."""

    def __init__(self) -> None:
        self.data: bytes | None = None
        self.saves = 0

    def load(self) -> tuple[Posted | None, str | None]:
        if self.data is None:
            return None, None
        return Posted.decode(self.data), str(hash(self.data))

    def save(self, posted: Posted, read: str | None) -> None:
        assert read == (None if self.data is None else str(hash(self.data))), "moved under it"
        self.data = posted.encode()
        self.saves += 1


@pytest.fixture
def world() -> dict:
    return {"rows": [], "slack": FakeSlackPost(), "store": FakeStore(), "routes": routes.parse("{}"),
            "queries": [], "outcome": None, "seen": 0}


def row(rule: str, severity: str, subject: str, started: str, ended: str | None = None,
        evidence: dict | None = None) -> dict:
    return {"rule_id": rule, "rule_version": "1", "subject": subject, "severity": severity,
            "started_at": at(started).replace(tzinfo=None), "ended_at": at(ended).replace(tzinfo=None) if ended else None,
            "evidence": json.dumps(evidence or {})}


@given(parsers.parse("the routes are '{text}'"))
def routes_are(world: dict, text: str) -> None:
    world["routes"] = routes.parse(text)


@given("the notifier has run before")
def run_before(world: dict) -> None:
    world["store"].data = Posted(started=at("09:00").isoformat()).encode()


@given(parsers.re(r'the open signal "(?P<rule>\w+)" "(?P<severity>\w+)" for "(?P<subject>[^"]*)" since '
                  r"(?P<clock>\d\d:\d\d)$"))
def open_signal(world: dict, rule: str, severity: str, subject: str, clock: str) -> None:
    world["rows"].append(row(rule, severity, subject, clock))


@given(parsers.re(r'the open signal "(?P<rule>\w+)" "(?P<severity>\w+)" for "(?P<subject>[^"]*)" since '
                  r"(?P<clock>\d\d:\d\d), with evidence '(?P<evidence>.*)'$"))
def open_signal_with(world: dict, rule: str, severity: str, subject: str, clock: str, evidence: str) -> None:
    world["rows"].append(row(rule, severity, subject, clock, evidence=json.loads(evidence)))


@given(parsers.re(r'the signal "(?P<rule>\w+)" "(?P<severity>\w+)" for "(?P<subject>[^"]*)" from '
                  r"(?P<start>\d\d:\d\d) to (?P<end>\d\d:\d\d)(?P<first>, its end read first)?$"))
def ended_signal(world: dict, rule: str, severity: str, subject: str, start: str, end: str, first: str) -> None:
    rows = [row(rule, severity, subject, start), row(rule, severity, subject, start, end)]
    world["rows"] += rows[::-1] if first else rows


@given(parsers.parse('the signal "{rule}" "{severity}" for "{subject}" ends at {clock}'))
def ends(world: dict, rule: str, severity: str, subject: str, clock: str) -> None:
    started = next(r for r in world["rows"] if r["rule_id"] == rule and r["subject"] == subject)["started_at"]
    world["rows"].append({**row(rule, severity, subject, "00:00", clock), "started_at": started})


@given("Slack refuses posts")
def refuses(world: dict) -> None:
    world["slack"].working = False


@given("Slack takes posts again")
def takes(world: dict) -> None:
    world["slack"].working = True


@given(parsers.re(r'the notifier remembers "(?P<rule>\w+)" for "(?P<subject>[^"]*)" from (?P<days>\d+) days ago, '
                  r"(?:ended (?P<ended>\d+) days ago|still open)$"))
def remembers(world: dict, rule: str, subject: str, days: str, ended: str | None) -> None:
    now = at("10:30")
    posted = Posted.decode(world["store"].data) if world["store"].data else Posted(started="x")
    signal = key(rule, subject, now - timedelta(days=int(days)))
    posted.mark(signal, "open", now - timedelta(days=int(days)))
    if ended:
        posted.mark(signal, "ended", now - timedelta(days=int(ended)))
    world["store"].data = posted.encode()


@when(parsers.parse("the notifier runs at {clock}"))
def runs(world: dict, clock: str) -> None:
    def query(sql: str) -> list[dict]:
        world["queries"].append(sql)
        return list(world["rows"])

    def post(channel: str, text: str) -> None:
        world["slack"].post(channel, text)

    world["seen"] = len(world["slack"].posted)
    world["saves"] = world["store"].saves
    world["outcome"] = notify.run(query, post, world["store"], world["routes"], at(clock),
                                  lambda s: links.signal_url(s.rule_id, s.subject, s.started_at))


def new_posts(world: dict) -> list[tuple[str, str]]:
    return world["slack"].posted[world["seen"]:]


@then("nothing is posted")
def nothing(world: dict) -> None:
    assert new_posts(world) == []


@then(parsers.parse('nothing is posted but "{channel}" "{text}"'))
def only(world: dict, channel: str, text: str) -> None:
    posts = new_posts(world)
    assert len(posts) == 1 and posts[0][0] == channel and posts[0][1].startswith(text), posts


@then(parsers.parse('"{channel}" gets "{text}"'))
def gets(world: dict, channel: str, text: str) -> None:
    assert any(c == channel and t.splitlines()[0] == text for c, t in new_posts(world)), new_posts(world)


@then("only one post is made")
def one(world: dict) -> None:
    assert len(new_posts(world)) == 1, new_posts(world)


@then(parsers.parse('the post says "{text}"'))
def says(world: dict, text: str) -> None:
    assert text in new_posts(world)[-1][1], new_posts(world)


@then(parsers.parse('the post links to "{url}"'))
def links_to(world: dict, url: str) -> None:
    assert new_posts(world)[-1][1].endswith(f"<{url}|What's behind it>"), new_posts(world)


@then("what was posted is saved")
def saved(world: dict) -> None:
    assert world["outcome"].saved and world["store"].saves == world["saves"] + 1


@then("nothing is saved")
def not_saved(world: dict) -> None:
    assert not world["outcome"].saved and world["store"].saves == world["saves"]


@then(parsers.parse('the run failed for "{what}"'))
def failed(world: dict, what: str) -> None:
    assert any(why.startswith(what) for why in world["outcome"].failed), world["outcome"].failed


@then(parsers.parse('it remembers only "{listed}"'))
def remembered(world: dict, listed: str) -> None:
    posted = Posted.decode(world["store"].data)
    assert [" ".join(json.loads(k)[:2]) for k in posted.signals] == [listed]


@then(parsers.parse('the query asked for "{text}"'))
def asked(world: dict, text: str) -> None:
    assert text in world["queries"][-1], world["queries"][-1]


def test_refused_is_the_clients_refusal() -> None:
    """FakeSlackPost refuses the way the real client does, with the library's Refused."""
    fake = FakeSlackPost(working=False)
    with pytest.raises(Refused):
        fake.post("C", "x")

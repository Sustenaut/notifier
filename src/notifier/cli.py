"""`notifier run`: one run, as the CronJob makes every two minutes.

Its settings are the environment:

| Variable | What |
|---|---|
| `NOTIFIER_ROUTES` | where signals go (routes.py) |
| `NOTIFIER_BIGQUERY_KEY` | notifier-reader's key: its JSON, or that JSON in base64 |
| `NOTIFIER_SLACK_TOKEN` | the Sustenaut bot's token |
| `NOTIFIER_STORAGE_URL` | storage's address, for what has been posted and the call log |
| `NOTIFIER_SITE` | where signals' pages are (optional; observability.sustenaut.eu) |

It exits 1 when a post or the state's write failed, so the CronJob's history shows
it, and 2 when a setting is missing or wrong.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from notifier import routes as routing

KEY = "NOTIFIER_BIGQUERY_KEY"
SLACK = "NOTIFIER_SLACK_TOKEN"
STORAGE = "NOTIFIER_STORAGE_URL"
SITE = "NOTIFIER_SITE"
# The project its call records belong to, as integrations' INGEST_DATASETS names it.
REPO = "notifier"
DATASET = "calls_notifier"
# Its sender's name in those records: one name, not the pod's, so each run's report
# is the same sender's and sender_silent can watch it.
SENDER = "notifier"
# The pod's projected service-account token for storage.
TOKEN_FILE = "/var/run/secrets/storage.sustenaut.eu/token"


def main(argv: list[str] | None = None, *, transport: Any = None, storage_token: Any = None) -> int:
    parser = argparse.ArgumentParser(prog="notifier", description="Posts observability's signals to Slack.")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("run", help="post what opened and ended since the last run")
    p.add_argument("--now", help="the moment to run at, ISO 8601 (for trying it out)")
    commands.add_parser("routes", help="check NOTIFIER_ROUTES and print where each kind of signal goes")
    args = parser.parse_args(argv)
    try:
        routes = routing.parse(os.environ.get(routing.VARIABLE, ""))
    except ValueError as error:
        print(f"notifier: {error}", file=sys.stderr)
        return 2
    if args.command == "routes":
        print(describe(routes))
        return 0
    try:
        return run(args.now, routes, transport, storage_token)
    except ValueError as error:
        print(f"notifier: {error}", file=sys.stderr)
        return 2


def describe(routes: routing.Routes) -> str:
    lines = [f"default\t{routes.default.channel if routes.default else '(none)'}\tfrom {routes.min_severity}"]
    for part, found in (("rule", routes.rules), ("subject", routes.subjects)):
        lines += [f"{part} {name}\t{r.channel}\tfrom {r.min_severity}" for name, r in sorted(found.items())]
    return "\n".join(lines)


def run(when: str | None, routes: routing.Routes, transport: Any,  # pragma: no cover - the pod's wiring
        storage_token: Any) -> int:
    from integrations.calls import Caller, IntegrationError, Network  # noqa: PLC0415 - the run's dependencies
    from integrations.clients.slack import SlackPost  # noqa: PLC0415
    from integrations.clients.storage import Storage  # noqa: PLC0415
    from observability import links  # noqa: PLC0415
    from observability.bigquery import Warehouse  # noqa: PLC0415
    from observability.cli import key  # noqa: PLC0415

    from notifier import notify, state  # noqa: PLC0415

    now = datetime.fromisoformat(when) if when else datetime.now(timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    url = os.environ.get(STORAGE, "")
    slack_token = os.environ.get(SLACK, "")
    if not url or not slack_token:
        raise ValueError(f"set {STORAGE} and {SLACK}")
    try:
        credentials = key(os.environ.get(KEY, ""))
    except ValueError:
        raise ValueError(f"{KEY} is not a service account's key") from None
    token_file = None if storage_token else Path(TOKEN_FILE)
    transport = transport or Network()
    sink = call_log(url, transport, storage_token, token_file)
    caller = Caller(REPO, "notifier", transport=transport, sink=sink)
    site = os.environ.get(SITE, links.SITE)
    store = state.StorageStore(Storage(caller, state.TENANT, base_url=url, token=storage_token,
                                       token_file=token_file))
    slack = SlackPost(caller, lambda: slack_token)
    try:
        outcome = notify.run(Warehouse(caller, credentials).query, slack.post, store, routes, now,
                             lambda s: links.signal_url(s.rule_id, s.subject, s.started_at, site))
    except IntegrationError as error:
        print(f"notifier: nothing more was posted: {error}", file=sys.stderr)
        return 1
    finally:
        if sink is not None:
            sink.flush()
    for channel, text in outcome.posted:
        print(f"posted to {channel}: {text.splitlines()[0]}")
    for why in outcome.failed:
        print(f"notifier: not posted, tried again next run: {why}", file=sys.stderr)
    if outcome.seeded:
        print("notifier: first run: what is open now is remembered, not posted", file=sys.stderr)
    return 1 if outcome.failed else 0


def call_log(url: str, transport: Any, storage_token: Any,  # pragma: no cover - the pod's wiring
             token_file: Path | None):  # noqa: ANN201
    """The notifier's own calls, to its buffer in storage, as every sender's are."""
    from integrations.storage_sink import StorageSink  # noqa: PLC0415

    def token() -> str:
        if storage_token:
            return storage_token()
        return token_file.read_text(encoding="utf-8").strip()

    return StorageSink({REPO: DATASET}, transport=transport, token=token, base_url=url,
                       sender=SENDER, start=False)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

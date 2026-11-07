"""What a post says, in Slack's mrkdwn. Everything that comes from a signal is
escaped, so a subject can't format, mention or link anything."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from notifier.notify import Signal

MARK = {"critical": ":red_circle:", "warning": ":large_orange_circle:", "info": ":large_blue_circle:"}
ENDED = ":white_check_mark:"
# The evidence a post shows; the signal's page shows it all.
EVIDENCE = 6


def escape(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def clock(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%H:%M UTC")


def minutes(start: datetime, end: datetime) -> str:
    return f"{max(0, int((end - start).total_seconds() // 60))} min"


def evidence(found: dict[str, Any]) -> str:
    shown = sorted(found.items())[:EVIDENCE]
    more = len(found) - len(shown)
    text = ", ".join(f"{escape(k)}: {escape(v)}" for k, v in shown)
    return text + (f", and {more} more" if more else "")


def text(signal: Signal, what: str, link: str) -> str:
    """`what` is "open", "ended", or "both" for one that opened and ended between runs."""
    name = f"{escape(signal.rule_id)} · `{escape(signal.subject)}`"
    details = f"<{link}|What's behind it>"
    if what == "ended":
        lasted = minutes(signal.started_at, signal.ended_at)
        return f"{ENDED} ended · {name} · lasted {lasted}\n{details}"
    mark = MARK.get(signal.severity, MARK["info"])
    head = f"{mark} *{escape(signal.severity)}* · {name}"
    if what == "both":
        head += (f" from {clock(signal.started_at)} to {clock(signal.ended_at)}"
                 f" ({minutes(signal.started_at, signal.ended_at)})")
    else:
        head += f" since {clock(signal.started_at)}"
    head += f" (rule v{escape(signal.rule_version)})"
    found = evidence(signal.evidence)
    return head + (f"\n{found}" if found else "") + f"\n{details}"


def started(open_count: int) -> str:
    return (f"The notifier has started. {open_count} signal{'s are' if open_count != 1 else ' is'} open now; "
            "it posts what opens and ends from here on.")

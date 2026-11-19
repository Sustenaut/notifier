"""What a post says, in Slack's mrkdwn. Everything that comes from a signal is
escaped, so a subject can't format, mention or link anything."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from notifier.notify import Signal

MARK = {"critical": ":red_circle:", "warning": ":large_orange_circle:", "info": ":large_blue_circle:"}
ENDED = ":white_check_mark:"
# The evidence a post shows; the signal's page shows it all.
EVIDENCE = 6
# The subjects a grouped post names; it counts the rest.
SUBJECTS = 10
SEVERITIES = ("critical", "warning", "info")


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


def grouped(signals: Sequence[Signal], what: str, links: Sequence[str]) -> str:
    """One post for several signals of one rule, all `what` ("open", "ended" or "both"):
    the rule, how many subjects, the earliest start, and each subject with its own link,
    the first SUBJECTS of them."""
    first = signals[0]
    count = f"{len(signals)} subjects"
    earliest = clock(min(s.started_at for s in signals))
    if what == "ended":
        head = f"{ENDED} ended · {escape(first.rule_id)} · {count}, the first since {earliest}"
    else:
        severity = min((s.severity for s in signals),
                       key=lambda found: SEVERITIES.index(found) if found in SEVERITIES else len(SEVERITIES))
        mark = MARK.get(severity, MARK["info"])
        versions = ", ".join(sorted({f"v{escape(s.rule_version)}" for s in signals}))
        when = f"opened and ended since {earliest}" if what == "both" else f"since {earliest}"
        head = f"{mark} *{escape(severity)}* · {escape(first.rule_id)} · {count} {when} (rule {versions})"
    lines = [f"• `{escape(s.subject)}` <{link}|What's behind it>" for s, link in zip(signals[:SUBJECTS], links)]
    more = len(signals) - SUBJECTS
    return "\n".join([head, *lines] + ([f"and {more} more"] if more > 0 else []))


def started(open_count: int) -> str:
    return (f"The notifier has started. {open_count} signal{'s are' if open_count != 1 else ' is'} open now; "
            "it posts what opens and ends from here on.")

"""Where each signal is posted, from NOTIFIER_ROUTES, a JSON object:

    {
      "default": "C0123",                 # a channel's id, or a person's for a DM
      "min_severity": "warning",          # critical, warning or info; warning if left out
      "rules": {"sender_silent": "C0456"},
      "subjects": {"example/app": {"channel": "C0789", "min_severity": "info"}}
    }

A subject's route wins over its rule's, and a rule's over the default. A route is
a channel, or an object with a `channel` and its own `min_severity`. A signal less
severe than its route's minimum isn't posted. Without a channel anywhere, it isn't
either. The value names consumers, so it is kept with the owner's state, not here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

VARIABLE = "NOTIFIER_ROUTES"
SEVERITIES = ("critical", "warning", "info")  # most severe first
KEYS = {"default", "min_severity", "rules", "subjects"}


@dataclass(frozen=True)
class Route:
    channel: str
    min_severity: str


@dataclass(frozen=True)
class Routes:
    default: Route | None
    min_severity: str
    rules: dict[str, Route]
    subjects: dict[str, Route]

    def route(self, rule_id: str, subject: str) -> Route | None:
        return self.subjects.get(subject) or self.rules.get(rule_id) or self.default

    def channel_for(self, rule_id: str, subject: str, severity: str) -> str | None:
        """The channel this signal goes to, or None when it isn't posted."""
        route = self.route(rule_id, subject)
        if route is None or rank(severity) > rank(route.min_severity):
            return None
        return route.channel


def rank(severity: str) -> int:
    """0 for the most severe; anything unknown counts as the least."""
    return SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES)


def _severity(value: object, where: str) -> str:
    if value not in SEVERITIES:
        raise ValueError(f"{VARIABLE}: {where} is one of {', '.join(SEVERITIES)}, not {value!r}")
    return str(value)


def _channel(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{VARIABLE}: {where} is a channel's or a person's id")
    return value.strip()


def _route(value: object, where: str, minimum: str) -> Route:
    if isinstance(value, dict):
        if unknown := sorted(set(value) - {"channel", "min_severity"}):
            raise ValueError(f"{VARIABLE}: {where} has no setting {', '.join(unknown)}")
        return Route(_channel(value.get("channel"), f"{where}'s channel"),
                     _severity(value.get("min_severity", minimum), f"{where}'s min_severity"))
    return Route(_channel(value, where), minimum)


def parse(text: str) -> Routes:
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        raise ValueError(f"{VARIABLE} is a JSON object")
    if unknown := sorted(set(data) - KEYS):
        raise ValueError(f"{VARIABLE} has no setting {', '.join(unknown)}")
    minimum = _severity(data.get("min_severity", "warning"), "min_severity")
    default = _route(data["default"], "default", minimum) if "default" in data else None
    out: dict[str, dict[str, Route]] = {}
    for part in ("rules", "subjects"):
        given = data.get(part, {})
        if not isinstance(given, dict):
            raise ValueError(f"{VARIABLE}: {part} maps each {part[:-1]} to its route")
        out[part] = {str(name): _route(value, f"{part}.{name}", minimum) for name, value in given.items()}
    return Routes(default, minimum, out["rules"], out["subjects"])

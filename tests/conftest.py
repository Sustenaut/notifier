"""The notifier's settings are the environment: a scenario starts with none of
them, whatever the shell running the suite has, and sets what it needs with
pubtest's environment steps."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def no_notifier_settings(monkeypatch) -> None:
    for name in [n for n in os.environ if n.startswith("NOTIFIER_")]:
        monkeypatch.delenv(name)

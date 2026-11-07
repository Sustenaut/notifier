"""Steps for `notifier routes`, and the checks `notifier run` makes before calling
anything, through bin/notifier."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("../features/routes.feature")

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def env() -> dict:
    keep = {k: v for k, v in os.environ.items() if not k.startswith("NOTIFIER_")}
    return {**keep, "PYTHONPATH": str(ROOT / "src")}


@given(parsers.re(r"NOTIFIER_ROUTES is '(?P<text>.*)'$"))
def routes_are(env: dict, text: str) -> None:
    env["NOTIFIER_ROUTES"] = text


@given(parsers.parse('the run\'s settings are there, but its key is "{text}"'))
def bad_key(env: dict, text: str) -> None:
    env.update(NOTIFIER_STORAGE_URL="https://storage.test", NOTIFIER_SLACK_TOKEN="xoxb-test",
               NOTIFIER_BIGQUERY_KEY=text)


@when(parsers.parse('I run notifier "{command}"'), target_fixture="result")
def run(env: dict, command: str) -> subprocess.CompletedProcess:
    # Through coverage when the suite runs under it, so the command's lines count.
    runner = [sys.executable, "-m", "coverage", "run", "--parallel-mode", "-m"] if os.environ.get(
        "COVERAGE_FILE") else [sys.executable, "-m"]
    return subprocess.run([*runner, "notifier", command], env=env, capture_output=True, text=True, check=False)


@then("it succeeds")
def succeeds(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stderr


@then(parsers.parse("it fails with {code:d}"))
def fails(result: subprocess.CompletedProcess, code: int) -> None:
    assert result.returncode == code, (result.stdout, result.stderr)


@then(parsers.parse('it prints "{text}"'))
def prints(result: subprocess.CompletedProcess, text: str) -> None:
    assert text.replace("\\t", "\t") in result.stdout.splitlines(), result.stdout


@then(parsers.parse('it says "{text}"'))
def says(result: subprocess.CompletedProcess, text: str) -> None:
    assert text in result.stderr, result.stderr

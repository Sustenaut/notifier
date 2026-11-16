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


@given(parsers.parse("the run's settings are there, but its credential file {how}"))
def bad_credential(env: dict, tmp_path, how: str) -> None:
    env.update(NOTIFIER_STORAGE_URL="https://storage.test", NOTIFIER_SLACK_TOKEN="xoxb-test")
    if how == "is not there":
        env["NOTIFIER_GOOGLE_CREDENTIAL_FILE"] = str(tmp_path / "none.json")
    elif how.startswith("holds "):
        (tmp_path / "credential.json").write_text(how.removeprefix("holds "), encoding="utf-8")
        env["NOTIFIER_GOOGLE_CREDENTIAL_FILE"] = str(tmp_path / "credential.json")


PROVIDER = ("//iam.googleapis.com/projects/948171295184/locations/global/workloadIdentityPools/services/"
            "providers/sustenaut-k3s")


@given("the manifests in k8s", target_fixture="manifests")
def manifests() -> dict:
    import json

    import yaml

    configmap = yaml.safe_load((ROOT / "k8s" / "google-credential.yaml").read_text(encoding="utf-8"))
    cronjob = next(d for d in yaml.safe_load_all((ROOT / "k8s" / "notifier.yaml").read_text(encoding="utf-8"))
                   if d and d["kind"] == "CronJob")
    return {"credential": json.loads(configmap["data"]["credential.json"]),
            "spec": cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]}


@then("the credential in google-credential.yaml acts as notifier-reader, audience the provider's")
def credential_is_the_readers(manifests: dict) -> None:
    credential = manifests["credential"]
    assert credential["type"] == "external_account" and credential["audience"] == PROVIDER
    assert credential["service_account_impersonation_url"].endswith(
        "/notifier-reader@sustenaut.iam.gserviceaccount.com:generateAccessToken")


@then("the CronJob runs as app, with no API token, and its projected token has that audience")
def token_audience(manifests: dict) -> None:
    spec = manifests["spec"]
    assert spec["serviceAccountName"] == "app" and spec["automountServiceAccountToken"] is False
    (volume,) = [v for v in spec["volumes"] if v["name"] == "google-token"]
    (source,) = volume["projected"]["sources"]
    assert source["serviceAccountToken"]["audience"] == PROVIDER


@then("the token and the credential are where the credential and NOTIFIER_GOOGLE_CREDENTIAL_FILE say")
def paths_agree(manifests: dict) -> None:
    spec = manifests["spec"]
    (volume,) = [v for v in spec["volumes"] if v["name"] == "google-token"]
    path = volume["projected"]["sources"][0]["serviceAccountToken"]["path"]
    (container,) = spec["containers"]
    mounts = {m["name"]: m["mountPath"] for m in container["volumeMounts"]}
    assert f"{mounts['google-token']}/{path}" == manifests["credential"]["credential_source"]["file"]
    env = {e["name"]: e.get("value") for e in container["env"]}
    assert env["NOTIFIER_GOOGLE_CREDENTIAL_FILE"] == f"{mounts['google-credential']}/credential.json"


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

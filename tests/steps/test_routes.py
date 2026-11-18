"""Steps for `notifier routes`, and the checks `notifier run` makes before calling
anything, through the package's own entry (`python -m notifier`), in-process."""

from __future__ import annotations

import json
import runpy
import shlex
from pathlib import Path

import yaml
from pytest_bdd import parsers, scenarios, when

scenarios("../features/routes.feature")

ROOT = Path(__file__).resolve().parents[2]


@when(parsers.parse('notifier is run with "{args}"'))
def run(ctx, monkeypatch, args: str) -> None:
    monkeypatch.setattr("sys.argv", ["notifier", *shlex.split(args)])
    ctx.attempt(lambda: runpy.run_module("notifier", run_name="__main__"))


def mounted() -> dict:
    """What google-auth finds in the CronJob's pod: the credential, the projected
    token it points at, and the variable that names the credential."""
    configmap = yaml.safe_load((ROOT / "k8s" / "google-credential.yaml").read_text(encoding="utf-8"))
    credential = json.loads(configmap["data"]["credential.json"])
    cronjob = next(d for d in yaml.safe_load_all((ROOT / "k8s" / "notifier.yaml").read_text(encoding="utf-8"))
                   if d and d["kind"] == "CronJob")
    spec = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    (volume,) = [v for v in spec["volumes"] if v["name"] == "google-token"]
    (source,) = volume["projected"]["sources"]
    (container,) = spec["containers"]
    mounts = {m["name"]: m["mountPath"] for m in container["volumeMounts"]}
    env = {e["name"]: e.get("value") for e in container["env"]}
    return {
        "credential": credential,
        "service account": spec["serviceAccountName"],
        "automount": spec["automountServiceAccountToken"],
        "token audience": source["serviceAccountToken"]["audience"],
        "token file": f"{mounts['google-token']}/{source['serviceAccountToken']['path']}",
        "credential file": f"{mounts['google-credential']}/credential.json",
        "NOTIFIER_GOOGLE_CREDENTIAL_FILE": env["NOTIFIER_GOOGLE_CREDENTIAL_FILE"],
    }


@when("google-auth reads the credential the CronJob mounts")
def reads_the_credential(ctx) -> None:
    ctx.attempt(mounted)

# notifier

Posts observability's signals to Slack: once when each opens, and once when it ends.
Each post links to the signal's own page, which gathers what lies behind it.

Observability gathers facts and derives signals by rule; it acts on nothing. The
notifier is the first thing that acts on them, and the only thing here that does.

## What it does

Every two minutes a CronJob on the shared k3s server runs `notifier run`:

1. **It reads** the signals written in the last day from BigQuery's
   `observability.signals`, as `notifier-reader`, which may read that table and nothing
   else. A signal is written twice, when it starts and when it ends, both with the same
   `started_at`, so a rule, a subject and that moment name it. The evaluator writes
   signals every two minutes and the integrations ingest pod loads them every two, so a
   signal reaches the notifier up to about four minutes after it was found.
2. **It posts** each signal's start once and its end once, by the Sustenaut Slack bot,
   to the channel its route names (below). One that opened and ended between two runs is
   posted once, as both. Each post links to
   `https://observability.sustenaut.eu/signals/<rule_id>/<started>/<subject>`, which
   `observability.links.signal_url` makes, so both repositories agree on it.
3. **It remembers** what it posted: a small JSON file in storage's private `notifier`
   tenant, named by the head `posted`. A run that posts something uploads a new file
   and moves the head to it with `If-Match` on the hash it read, so two runs can't
   both win. Signals that ended are forgotten after 7 days, and any after 30.

A post Slack refuses isn't remembered, so the next run tries it again, and the run
exits 1. Posting comes before remembering, so a run that dies between the two posts
again next time: a signal may be posted twice, never left out.

**The first run**, with nothing remembered, posts nothing it finds. It remembers it all
and posts one line to the default channel: that it has started, and how many signals
are open.

A signal no route posts, such as one below its route's minimum severity, is remembered
too, so a route added later doesn't post what happened before it.

Its own calls (BigQuery, Slack and storage) go to its call log, through the integrations
library's `StorageSink`, into storage's `calls-notifier` buffer and BigQuery's
`calls_notifier`, as every sender's do. Listed as an always-on sender in observability's
`OBSERVABILITY_SENDERS`, its silence is a `sender_silent` signal, though one it can't post
about itself: its failed runs are in the CronJob's history.

## Routes

Where each signal goes is the repository variable `NOTIFIER_ROUTES`, a JSON object:

```json
{
  "default": "C0123",
  "min_severity": "warning",
  "rules": {"sender_silent": "C0456"},
  "subjects": {"example/app": {"channel": "C0789", "min_severity": "info"}}
}
```

- A route is a channel's id, or a person's for a direct message, or an object with a
  `channel` and its own `min_severity`.
- A subject's route wins over its rule's, and a rule's over the default.
- `min_severity` is `critical`, `warning` or `info`, and `warning` if left out, so
  `info` signals such as `cold_start_share` aren't posted unless a route asks for them.
- The bot must be in each channel it posts to; a direct message needs nothing more.

Subjects name consumers, so the value isn't kept here: `pubkit.json`'s `variables` block
declares the name, and the owner's state repository keeps the value and sets it
(`pubfleet variables --apply`). `notifier routes` checks it and prints each route:

```sh
NOTIFIER_ROUTES='{"default": "C0123"}' PYTHONPATH=src python3 -m notifier routes
```

## Settings

| Variable | What |
|---|---|
| `NOTIFIER_ROUTES` | where signals go (above) |
| `NOTIFIER_BIGQUERY_KEY` | `notifier-reader`'s key: its JSON, or that JSON in base64 |
| `NOTIFIER_SLACK_TOKEN` | the Sustenaut bot's token |
| `NOTIFIER_STORAGE_URL` | storage's address |
| `NOTIFIER_SITE` | where signals' pages are (optional; `https://observability.sustenaut.eu`) |

The pod reads storage with its projected service-account token,
`/var/run/secrets/storage.sustenaut.eu/token`, as `k8s:notifier/app`.

## Deploying

`.github/workflows/deploy.yml` builds the image (`Dockerfile`, from the hash-locked
`requirements.lock`) on each merge to main and applies `k8s/` with pubkit's
`k8s-deploy.yml`, once `DEPLOY_NOTIFIER` is `on`. The routes become the ConfigMap
`notifier-settings`.

What it needs elsewhere: shared-infra's `notifier-reader` account and `calls_notifier`
dataset (`infra/notifier.tf`, `infra/call_log.tf`), storage's `notifier` and
`calls-notifier` tenants, and its entries in other repositories' variables. pubkit.json's
`deploy` block lists them with everything else it needs, and pubkit's deploy walk checks
each and makes what it can. To take it live, or bring it back in step, from a checkout of
this repository with Sustenaut/shared-infra checked out beside it, on a machine on the
admin tailnet, signed in to `gh` and `gcloud`:

```sh
./with-secrets ./pubdeploy walk --fulfil --server sustenaut --zones ../shared-infra/pubkit.json
```

It checks every need, prints the plan, and waits for a typed `yes`; then it makes each
missing need it can, over the admin channel (`ssh root@sustenaut`), and checks it again.
Every run can run again: what is ready is left alone. In order:

| Need | What the walk does |
|---|---|
| the namespace `notifier` | the server's `sustenaut-app`, which makes it and its deploy identity |
| `gcp.service-account-key` | a new key of `notifier-reader` (Terraform's, in shared-infra), written to Bitwarden as `notifier-reader-key`, then put in the Secret `notifier-secrets` as `bigquery-key.json`. A key that is no longer one of the account's live keys is drift, and a new one is made |
| `bitwarden.secret` | `slack-bot-token`, the Sustenaut bot's, read from Bitwarden and put in the same Secret as `slack-token` |
| the repository's secrets and deploy settings | from Bitwarden, as `pubsec app-secrets` sends them |
| `DEPLOY_NOTIFIER` and the rollout | the gate on, once everything before it is ready, and `deploy.yml` run and waited for |
| `k8s.cronjob` | the CronJobs `notifier` and `fake-sender` succeeded within two runs; one that hasn't, a Job from it, waited for |

A new key wants a Bitwarden token that may write: the walk asks for it once, at a hidden
prompt, and keeps it only in its process. The first run after a deploy posts nothing old:
it remembers what is there and says it has started.

Some needs it only checks, and says what a person does:

- **storage's tenants** in Sustenaut/storage's `tenants.json`: `notifier` (private, with
  heads), which `k8s:notifier/app` reads and writes, and `calls-notifier` (private, an
  inbox), its call log buffer, which it writes. When one is missing, the fix is the entry
  to add there.
- **The entries in other repositories' variables**, kept in the owner's state file and set
  with `pubfleet variables --apply`: integrations' `INGEST_DATASETS` loads `notifier` into
  `calls_notifier`, and observability's `OBSERVABILITY_SENDERS` expects `notifier/notifier`
  and `notifier/e2e` always on. `NOTIFIER_ROUTES` must be set, with a `default` route and
  one for the subject `notifier/e2e` (for the silence test below).
- **storage itself** (`upstream`).

`./pubdeploy walk` without `--fulfil` (or `pubdeploy check`) changes nothing, and
`./pubdeploy walk --offline` checks only the files. `.github/workflows/deploy-check.yml`
walks it every 30 minutes, read-only, with the deploy key, and writes the walk to
storage's `plane` tenant; it fails when a need is missing, drift or blocked.

## Testing it live

The notifier tests itself against the live services, with nothing taken down, through a
fake sender: `notifier fake-sender` reports as a sender that exists only to be watched,
through the same `StorageSink` every real sender writes with, into its own call log
buffer, as `k8s:notifier/app`. So it needs no other grant, key or dataset.

- **The steady fake sender, `e2e`:** the CronJob `fake-sender` (`k8s/fake-sender.yaml`)
  reports as it every two minutes. Observability expects it always on
  (`OBSERVABILITY_SENDERS`), so it is a healthy sender until something pauses it.
- **The silence test**, `./with-secrets k8s/admin/e2e.sh`, about 20 minutes:
  1. It waits, up to 10 minutes, until the route for `notifier/e2e` is in the settings
     the notifier runs with and the fake sender is deployed and reporting, so it can
     run straight after a change to either merges. It says what is missing, and what
     to run, if they don't arrive. Then it posts to the test channel, which checks that
     the bot is in it.
  2. It pauses the fake sender, and waits for the notifier to post `sender_silent`'s
     opening for `notifier/e2e`, with its page's link.
  3. It resumes the sender and waits for the end.
  4. It checks that each was posted once.

  It resumes the sender however it stops. `NOTIFIER_ROUTES` sends the subject
  `notifier/e2e` to a test channel of its own, so the test stays out of the others.
- **Load:** `./with-secrets k8s/admin/e2e.sh load --senders 50 --minutes 10 --calls 20`
  runs a one-off Job of 50 fake senders (`e2e-a`, `e2e-b`, ...). Each reports 20 calls
  to the made-up plugin `e2e.fake` every two minutes, for 10 minutes, after which the
  Job is deleted. Observability doesn't expect them, so they make no signal when they
  stop. Their calls show on the trends page under `e2e.fake`.

## Working on it

```sh
make venv        # .venv from the hash-locked test requirements
make check       # everything CI runs
```

The suite runs against fakes for BigQuery (rows a query answers), Slack (the
integrations library's `FakeSlackPost`) and storage (a head in memory, moved with
`If-Match`), at 100% line coverage.

## Licence

Apache-2.0.

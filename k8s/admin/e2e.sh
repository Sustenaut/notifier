#!/usr/bin/env bash
# The notifier's end-to-end test, against the live services, with nothing taken down.
# From this repository's root, on a machine on Sustenaut's admin tailnet:
#
#   ./with-secrets k8s/admin/e2e.sh                            # the silence test
#   ./with-secrets k8s/admin/e2e.sh load --senders 50 --minutes 10 [--calls 20]
#
# The silence test pauses the steady fake sender, e2e (k8s/fake-sender.yaml), which
# observability expects always on. It checks that the notifier posts sender_silent's
# opening for notifier/e2e once, with its page's link; then resumes the sender and
# checks that the end is posted once. It resumes the sender however it stops. About 20
# minutes: the rule waits 6 minutes of silence, and the evaluator, the ingest pod and the
# notifier each run every two.
#
# Load runs a one-off Job of N fake senders (e2e-a, e2e-b, ...), each with --calls
# made-up calls every two minutes, for --minutes, then deletes it. Observability doesn't
# expect them, so they make no signal when they stop.
#
# It needs NOTIFIER_ROUTES to route the subject notifier/e2e to a test channel, the
# Sustenaut bot in that channel (it posts there first, to check), SLACK_BOT_TOKEN from
# Bitwarden, gh, and root SSH to the server. It prints no secret.
set -euo pipefail

server=${SUSTENAUT_SERVER:-sustenaut}
repo=Sustenaut/notifier
subject=notifier/e2e
k() { ssh "root@$server" "k3s kubectl -n notifier $*"; }

if [[ "${1:-}" = load ]]; then
  shift
  senders=10 minutes=10 calls=10
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --senders) senders=$2; shift 2 ;;
      --minutes) minutes=$2; shift 2 ;;
      --calls) calls=$2; shift 2 ;;
      *) echo "e2e: no option $1" >&2; exit 2 ;;
    esac
  done
  job="fake-load-$(date +%s)"
  echo "e2e: $senders fake senders, $calls calls each every two minutes, for $minutes minutes, as job $job"
  k "create job $job --from=cronjob/fake-sender --dry-run=client -o json" \
    | jq --argjson s "$senders" --argjson m "$minutes" --argjson c "$calls" '
        .spec.activeDeadlineSeconds = ($m * 60 + 120)
        | .spec.template.spec.containers[0].command =
            ["notifier", "fake-sender", "--senders", ($s|tostring), "--calls", ($c|tostring),
             "--minutes", ($m|tostring)]' \
    | ssh "root@$server" 'k3s kubectl -n notifier apply -f -' > /dev/null
  trap 'k "delete job $job --ignore-not-found" > /dev/null' EXIT
  k "wait --for=condition=complete --timeout=$((minutes * 60 + 180))s job/$job" > /dev/null
  k "logs job/$job" | tail -3
  echo "e2e: load done; the job is deleted"
  exit 0
fi

[[ -n "${SLACK_BOT_TOKEN:-}" ]] || { echo "e2e: SLACK_BOT_TOKEN isn't set: run this through ./with-secrets" >&2; exit 2; }
channel=$(gh api "repos/$repo/actions/variables/NOTIFIER_ROUTES" -q .value \
  | jq -r --arg s "$subject" '.subjects[$s] // empty | if type == "object" then .channel else . end')
[[ -n "$channel" ]] || {
  echo "e2e: NOTIFIER_ROUTES has no subjects route for $subject: give it a test channel" \
    "(the owner's state repository), so the test's posts stay out of the others" >&2
  exit 2
}

# The bot's token reaches curl as a header file, never on its command line.
said=$(curl -sS https://slack.com/api/chat.postMessage -H @<(printf 'Authorization: Bearer %s\n' "$SLACK_BOT_TOKEN") \
  --data-urlencode "channel=$channel" \
  --data-urlencode "text=The notifier's end-to-end test is starting: it pauses the fake sender e2e, and expects one post here when $subject goes silent, and one when it reports again.")
if [[ "$(jq -r .ok <<<"$said")" != true ]]; then
  why=$(jq -r .error <<<"$said")
  case "$why" in
    not_in_channel|channel_not_found) echo "e2e: the Sustenaut bot isn't in $channel ($why): invite it there, and run this again" >&2 ;;
    *) echo "e2e: Slack refused the test's first post: $why" >&2 ;;
  esac
  exit 1
fi

seen=$(mktemp)
resume() { k "patch cronjob fake-sender -p '{\"spec\":{\"suspend\":false}}'" > /dev/null; }
trap 'resume; rm -f "$seen"' EXIT

# Every post the notifier's runs have logged for the subject, kept as they're seen:
# a run's log lasts only as long as its job is kept.
collect() {
  ssh "root@$server" "for j in \$(k3s kubectl -n notifier get jobs -o name | grep '/notifier-'); do
      k3s kubectl -n notifier logs \$j 2>/dev/null | sed \"s|^|\$j\t|\"; done" \
    | grep -F "sender_silent · \`$subject\`" >> "$seen" || true
  sort -u -o "$seen" "$seen"
}

# A run's lines, for one kind of post: "since" an opening, "ended" an end.
count() { cut -f2- "$seen" | grep -c -- "$1" || true; }

wait_for() {
  local what=$1 minutes=$2
  for _ in $(seq $((minutes * 2))); do
    collect
    [[ "$(count "$what")" -ge 1 ]] && return 0
    sleep 30
  done
  echo "e2e: no post with \"$what\" for $subject in $minutes minutes" >&2
  exit 1
}

echo "1/4 pausing the fake sender e2e"
k "patch cronjob fake-sender -p '{\"spec\":{\"suspend\":true}}'" > /dev/null
echo "2/4 waiting for the notifier to post that $subject went silent (about 10 minutes)"
wait_for "since" 25
opening=$(cut -f2- "$seen" | grep -- "since" | head -1)
echo "  $opening"
grep -q "https://observability.sustenaut.eu/signals/sender_silent/" <<<"$opening" \
  || { echo "e2e: the opening has no link to the signal's page" >&2; exit 1; }
echo "3/4 resuming the fake sender, and waiting for the end (about 6 minutes)"
resume
wait_for "ended" 20
echo "  $(cut -f2- "$seen" | grep -- "ended" | head -1)"
echo "4/4 two more runs, to see that neither is posted again"
for _ in 1 2 3 4 5 6 7 8 9 10; do collect; sleep 30; done
opened=$(count "since") ended=$(count "ended")
[[ "$opened" = 1 && "$ended" = 1 ]] \
  || { echo "e2e: posted $opened openings and $ended ends for $subject, not one each" >&2; exit 1; }
echo "e2e: passed: one post when $subject went silent, with its link, and one when it reported again"

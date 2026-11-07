#!/usr/bin/env bash
# Takes the notifier live, or brings it back in step. Every step can run again. From this
# repository's root, on a machine on Sustenaut's admin tailnet:
#
#   ./with-secrets k8s/admin/go-live.sh
#
# It needs, in Bitwarden's Sustenaut project, notifier-reader-key (shared-infra's
# help/setup.md makes it), slack-bot-token, and every name pubkit.json's secrets list
# gives; the repository variable NOTIFIER_ROUTES (not a secret, so not in Bitwarden; the
# owner's state repository keeps it); gh signed in as an admin of Sustenaut/notifier;
# and root SSH to the server. It prints no secret.
#
#   0. NOTIFIER_ROUTES is set, or it stops and says how to set it
#   1. the namespace notifier and its deploy identity (the server's sustenaut-app)
#   2. the BigQuery key and the Slack token, as the Secret notifier-secrets: the deploy
#      identity may not manage Secrets, so it goes over the admin key
#   3. the repository's secrets and deploy settings, from Bitwarden: pubkit app-secrets
#   4. DEPLOY_NOTIFIER on, a deploy, and its wait
#   5. one run now, and its log. The first run posts nothing old: it remembers what is
#      there and says it has started.
set -euo pipefail

: "${NOTIFIER_READER_KEY:?not set: run this through ./with-secrets, after making the key (shared-infra help/setup.md)}"
: "${SLACK_BOT_TOKEN:?not set: run this through ./with-secrets}"
server=${SUSTENAUT_SERVER:-sustenaut}
repo=Sustenaut/notifier
root=$(cd "$(dirname "$0")/../.." && pwd)

echo "0/5 the routes"
gh variable list -R "$repo" --json name -q '.[].name' | grep -qx NOTIFIER_ROUTES || {
  echo "go-live: NOTIFIER_ROUTES isn't set on $repo. Set it from the owner's state repository" \
    "(pubkit variables --apply), or with gh variable set NOTIFIER_ROUTES -R $repo --body '{\"default\": \"C…\"}'," \
    "and run this again." >&2
  exit 1
}

echo "1/5 the namespace and its deploy identity"
ssh "root@$server" sustenaut-app notifier

echo "2/5 the BigQuery key and the Slack token, as the Secret notifier-secrets"
# jq reads both from its environment, so neither is on a command line. pubkit
# service-account-key create stores a key base64-encoded, as a Secret's data holds it.
jq -n '{apiVersion: "v1", kind: "Secret", metadata: {name: "notifier-secrets", namespace: "notifier"},
        type: "Opaque",
        data: {"bigquery-key.json": (env.NOTIFIER_READER_KEY | gsub("\\s"; "")),
               "slack-token": (env.SLACK_BOT_TOKEN | @base64)}}' \
  | ssh "root@$server" 'k3s kubectl apply -f -'

echo "3/5 the repository's secrets and deploy settings, from Bitwarden"
"$root/pubkit" app-secrets

echo "4/5 deploying"
gh variable set DEPLOY_NOTIFIER -R "$repo" --body on
before=$(gh run list -R "$repo" -w deploy.yml -L 1 --json databaseId -q '.[0].databaseId // 0')
gh workflow run deploy.yml -R "$repo" --ref main
run=$before
for _ in $(seq 30); do
  run=$(gh run list -R "$repo" -w deploy.yml -L 1 --json databaseId -q '.[0].databaseId // 0')
  [ "$run" != "$before" ] && break
  sleep 2
done
[ "$run" != "$before" ] || { echo "go-live: the deploy didn't start" >&2; exit 1; }
gh run watch "$run" -R "$repo" --exit-status > /dev/null

echo "5/5 one run now"
job="notifier-go-live-$(date +%s)"
ssh "root@$server" "k3s kubectl -n notifier create job $job --from=cronjob/notifier > /dev/null \
  && k3s kubectl -n notifier wait --for=condition=complete --timeout=150s job/$job; \
  k3s kubectl -n notifier logs job/$job"
echo "go-live: done; the notifier runs every two minutes"

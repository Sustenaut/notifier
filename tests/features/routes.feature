Feature: Where signals go

  NOTIFIER_ROUTES names a default channel, and channels for rules and subjects, each
  with a minimum severity. `notifier routes` checks it and prints it.

  Scenario: The routes are printed, most specific last
    Given the environment sets "NOTIFIER_ROUTES" to "{"default": "C1", "rules": {"drops": {"channel": "C2", "min_severity": "critical"}}, "subjects": {"a/b": "C3"}}"
    When notifier is run with "routes"
    Then it succeeds
    And it prints:
      """
      default	C1	from warning
      rule drops	C2	from critical
      subject a/b	C3	from warning
      """

  Scenario: With none set, nothing has a route
    Given the environment does not set "NOTIFIER_ROUTES"
    When notifier is run with "routes"
    Then it succeeds
    And it prints:
      """
      default	(none)	from warning
      """

  Scenario Outline: Routes that are wrong are refused, and say why
    Given the environment sets "NOTIFIER_ROUTES" to "<routes>"
    When notifier is run with "routes"
    Then the exit code is 2
    And stderr mentions "<message>"

    Examples:
      | routes                                                | message                                                    |
      | []                                                    | NOTIFIER_ROUTES is a JSON object                           |
      | {"channels": {}}                                      | NOTIFIER_ROUTES has no setting channels                    |
      | {"min_severity": "loud"}                              | min_severity is one of critical, warning, info, not 'loud' |
      | {"default": ""}                                       | default is a channel's or a person's id                    |
      | {"rules": []}                                         | rules maps each rule to its route                          |
      | {"rules": {"r": {"channel": "C", "to": "x"}}}         | rules.r has no setting to                                  |
      | {"rules": {"r": {"channel": "C", "min_severity": 1}}} | rules.r's min_severity is one of critical, warning, info   |
      | {"subjects": {"s": {"min_severity": "info"}}}         | subjects.s's channel is a channel's or a person's id       |

  Scenario: A run without its settings stops before calling anything
    Given the environment sets "NOTIFIER_ROUTES" to "{"default": "C1"}"
    When notifier is run with "run"
    Then the exit code is 2
    And stderr mentions "set NOTIFIER_STORAGE_URL and NOTIFIER_SLACK_TOKEN"

  Scenario: A run with no Google credential file stops too
    Given the environment sets "NOTIFIER_ROUTES" to "{"default": "C1"}"
    And the environment sets "NOTIFIER_STORAGE_URL" to "https://storage.test"
    And the environment sets "NOTIFIER_SLACK_TOKEN" to "xoxb-test"
    When notifier is run with "run"
    Then the exit code is 2
    And stderr mentions "no credential: set NOTIFIER_GOOGLE_CREDENTIAL_FILE"

  Scenario: A run whose Google credential file is not there stops too
    Given a scratch directory
    And the environment sets "NOTIFIER_ROUTES" to "{"default": "C1"}"
    And the environment sets "NOTIFIER_STORAGE_URL" to "https://storage.test"
    And the environment sets "NOTIFIER_SLACK_TOKEN" to "xoxb-test"
    And the environment sets "NOTIFIER_GOOGLE_CREDENTIAL_FILE" to "none.json"
    When notifier is run with "run"
    Then the exit code is 2
    And stderr mentions "NOTIFIER_GOOGLE_CREDENTIAL_FILE is not a readable JSON file"

  Scenario: A run whose Google credential file is no credential stops too
    Given a scratch directory
    And a file "credential.json" holding "{"not": "a key"}"
    And the environment sets "NOTIFIER_ROUTES" to "{"default": "C1"}"
    And the environment sets "NOTIFIER_STORAGE_URL" to "https://storage.test"
    And the environment sets "NOTIFIER_SLACK_TOKEN" to "xoxb-test"
    And the environment sets "NOTIFIER_GOOGLE_CREDENTIAL_FILE" to "credential.json"
    When notifier is run with "run"
    Then the exit code is 2
    And stderr mentions "NOTIFIER_GOOGLE_CREDENTIAL_FILE is neither an external_account credential nor a service account's key"

  Scenario: The CronJob's token, its credential and the services pool's provider name one audience
    When google-auth reads the credential the CronJob mounts
    Then the result's "credential.type" is "external_account"
    And the result's "credential.audience" is "//iam.googleapis.com/projects/948171295184/locations/global/workloadIdentityPools/services/providers/sustenaut-k3s"
    And the result's "credential.service_account_impersonation_url" is "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/notifier-reader@sustenaut.iam.gserviceaccount.com:generateAccessToken"
    And the result's "service account" is "app"
    And the result's "automount" is "false"
    And the result's "token audience" is "//iam.googleapis.com/projects/948171295184/locations/global/workloadIdentityPools/services/providers/sustenaut-k3s"
    And the result's "token file" is "/var/run/secrets/google/token"
    And the result's "credential.credential_source.file" is "/var/run/secrets/google/token"
    And the result's "credential file" is "/etc/google/credential.json"
    And the result's "NOTIFIER_GOOGLE_CREDENTIAL_FILE" is "/etc/google/credential.json"

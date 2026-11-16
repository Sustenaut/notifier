Feature: Where signals go

  NOTIFIER_ROUTES names a default channel, and channels for rules and subjects, each
  with a minimum severity. `notifier routes` checks it and prints it.

  Scenario: The routes are printed, most specific last
    Given NOTIFIER_ROUTES is '{"default": "C1", "rules": {"drops": {"channel": "C2", "min_severity": "critical"}}, "subjects": {"a/b": "C3"}}'
    When I run notifier "routes"
    Then it succeeds
    And it prints "default\tC1\tfrom warning"
    And it prints "rule drops\tC2\tfrom critical"
    And it prints "subject a/b\tC3\tfrom warning"

  Scenario: With none set, nothing has a route
    Given NOTIFIER_ROUTES is ''
    When I run notifier "routes"
    Then it prints "default\t(none)\tfrom warning"

  Scenario Outline: Routes that are wrong are refused, and say why
    Given NOTIFIER_ROUTES is '<routes>'
    When I run notifier "routes"
    Then it fails with 2
    And it says "<message>"

    Examples:
      | routes                                              | message                                                      |
      | []                                                  | NOTIFIER_ROUTES is a JSON object                             |
      | {"channels": {}}                                    | NOTIFIER_ROUTES has no setting channels                      |
      | {"min_severity": "loud"}                            | min_severity is one of critical, warning, info, not 'loud'   |
      | {"default": ""}                                     | default is a channel's or a person's id                      |
      | {"rules": []}                                       | rules maps each rule to its route                            |
      | {"rules": {"r": {"channel": "C", "to": "x"}}}       | rules.r has no setting to                                    |
      | {"rules": {"r": {"channel": "C", "min_severity": 1}}} | rules.r's min_severity is one of critical, warning, info |
      | {"subjects": {"s": {"min_severity": "info"}}}       | subjects.s's channel is a channel's or a person's id         |

  Scenario: A run without its settings stops before calling anything
    Given NOTIFIER_ROUTES is '{"default": "C1"}'
    When I run notifier "run"
    Then it fails with 2
    And it says "set NOTIFIER_STORAGE_URL and NOTIFIER_SLACK_TOKEN"

  Scenario Outline: A run whose Google credential file isn't one stops too
    Given NOTIFIER_ROUTES is '{"default": "C1"}'
    And the run's settings are there, but its credential file <file>
    When I run notifier "run"
    Then it fails with 2
    And it says "<words>"

    Examples:
      | file                  | words                                                                                       |
      | is not set            | no credential: set NOTIFIER_GOOGLE_CREDENTIAL_FILE                                          |
      | is not there          | NOTIFIER_GOOGLE_CREDENTIAL_FILE is not a readable JSON file                                 |
      | holds {"not": "a key"} | NOTIFIER_GOOGLE_CREDENTIAL_FILE is neither an external_account credential nor a service account's key |

  Scenario: The CronJob's token, its credential and the services pool's provider name one audience
    Given the manifests in k8s
    Then the credential in google-credential.yaml acts as notifier-reader, audience the provider's
    And the CronJob runs as app, with no API token, and its projected token has that audience
    And the token and the credential are where the credential and NOTIFIER_GOOGLE_CREDENTIAL_FILE say

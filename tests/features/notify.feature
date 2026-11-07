Feature: Posting each signal once when it opens and once when it ends

  The notifier reads the last day's signals from observability.signals and posts
  each start and end once, to the channel its route names, remembering what it
  posted in storage. Here BigQuery, Slack and storage are fakes, and it runs at 10:30.

  Background:
    Given the routes are '{"default": "C-DEFAULT", "rules": {"sender_silent": "C-PAGER"}, "subjects": {"example/web": {"channel": "C-WEB", "min_severity": "info"}}}'

  Scenario: The first run posts nothing old, says it has started, and remembers it all
    Given the open signal "drops" "warning" for "example/app" since 10:20
    And the signal "storage_unreachable" "critical" for "example" from 09:00 to 09:30
    When the notifier runs at 10:30
    Then nothing is posted but "C-DEFAULT" "The notifier has started. 1 signal is open now"
    And what was posted is saved
    When the notifier runs at 10:32
    Then nothing is posted
    And nothing is saved

  Scenario: A signal is posted when it opens, and again when it ends
    Given the notifier has run before
    And the open signal "sender_silent" "critical" for "example/app" since 10:20
    When the notifier runs at 10:30
    Then "C-PAGER" gets ":red_circle: *critical* · sender_silent · `example/app` since 10:20 UTC (rule v1)"
    And the post links to "https://observability.sustenaut.eu/signals/sender_silent/20261101T102000Z/example/app"
    When the notifier runs at 10:32
    Then nothing is posted
    Given the signal "sender_silent" "critical" for "example/app" ends at 10:34
    When the notifier runs at 10:36
    Then "C-PAGER" gets ":white_check_mark: ended · sender_silent · `example/app` · lasted 14 min"
    When the notifier runs at 10:38
    Then nothing is posted

  Scenario: A signal that opened and ended between two runs is posted once, as both
    Given the notifier has run before
    And the signal "drops" "warning" for "example/app" from 10:21 to 10:25
    When the notifier runs at 10:30
    Then "C-DEFAULT" gets ":large_orange_circle: *warning* · drops · `example/app` from 10:21 UTC to 10:25 UTC (4 min) (rule v1)"
    And only one post is made

  Scenario: The evidence is shown, escaped, and cut short
    Given the notifier has run before
    And the open signal "drops" "warning" for "<!channel> & co" since 10:20, with evidence '{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": "<x>", "g": 7, "h": 8}'
    When the notifier runs at 10:30
    Then the post says "`&lt;!channel&gt; &amp; co`"
    And the post says "a: 1, b: 2, c: 3, d: 4, e: 5, f: &lt;x&gt;, and 2 more"
    And the post links to "https://observability.sustenaut.eu/signals/drops/20261101T102000Z/%3C%21channel%3E%20%26%20co"

  Scenario: A subject's route wins over its rule's, with its own minimum severity
    Given the notifier has run before
    And the open signal "cold_start_share" "info" for "example/web" since 10:20
    And the open signal "cold_start_share" "info" for "example/app" since 10:20
    When the notifier runs at 10:30
    Then "C-WEB" gets ":large_blue_circle: *info* · cold_start_share · `example/web` since 10:20 UTC (rule v1)"
    And only one post is made

  Scenario: A signal below its route's minimum is never posted, even once a route would take it
    Given the notifier has run before
    And the open signal "cold_start_share" "info" for "example/app" since 10:20
    When the notifier runs at 10:30
    Then nothing is posted
    And what was posted is saved
    Given the routes are '{"default": "C-DEFAULT", "min_severity": "info"}'
    When the notifier runs at 10:32
    Then nothing is posted

  Scenario: With no route at all, nothing is posted, the first run included
    Given the routes are '{}'
    And the open signal "drops" "warning" for "example/app" since 10:20
    When the notifier runs at 10:30
    Then nothing is posted
    And what was posted is saved

  Scenario: A post Slack refuses is tried again next run, and the run says so
    Given the notifier has run before
    And the open signal "drops" "warning" for "example/app" since 10:20
    And Slack refuses posts
    When the notifier runs at 10:30
    Then nothing is posted
    And the run failed for "drops example/app"
    Given Slack takes posts again
    When the notifier runs at 10:32
    Then "C-DEFAULT" gets ":large_orange_circle: *warning* · drops · `example/app` since 10:20 UTC (rule v1)"

  Scenario: A first message Slack refuses fails the run, and the state is still saved
    Given the open signal "drops" "warning" for "example/app" since 10:20
    And Slack refuses posts
    When the notifier runs at 10:30
    Then the run failed for "the first message"
    And what was posted is saved

  Scenario: What it remembers is pruned: an ended signal after a week, any after 30 days
    Given the notifier remembers "drops" for "example/app" from 10 days ago, ended 8 days ago
    And the notifier remembers "drops" for "example/web" from 10 days ago, ended 6 days ago
    And the notifier remembers "sender_silent" for "example/app" from 31 days ago, still open
    When the notifier runs at 10:30
    Then it remembers only "drops example/web"

  Scenario: The query reads the last day's starts and ends, from the last 30 days' signals
    When the notifier runs at 10:30
    Then the query asked for "emitted_at >= TIMESTAMP_SUB(TIMESTAMP '2026-11-01 10:30:00+00:00', INTERVAL 1 DAY)"

  Scenario: A signal read twice in one run, as its start and as its end, is the ended one
    Given the notifier has run before
    And the signal "drops" "warning" for "example/app" from 10:21 to 10:25, its end read first
    When the notifier runs at 10:30
    Then "C-DEFAULT" gets ":large_orange_circle: *warning* · drops · `example/app` from 10:21 UTC to 10:25 UTC (4 min) (rule v1)"

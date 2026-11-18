Feature: Made-up senders, for tests

  `notifier fake-sender` reports as senders that exist only to be watched, through
  the same StorageSink every real sender writes with, into the notifier's call log
  buffer. Here storage is a fake that takes every file.

  Scenario Outline: One sender is the steady e2e; more are named by letters alone
    When <count> fake senders are named
    Then the result has <count> names
    And the result's "0" is "<first>"
    And the result's "-1" is "<last>"
    And no item of the result is there twice

    Examples:
      | count | first | last    |
      | 1     | e2e   | e2e     |
      | 3     | e2e-a | e2e-c   |
      | 28    | e2e-a | e2e-ab  |

  Scenario: Each cycle writes each sender's calls and then its report, every two minutes
    When 2 fake senders report 3 calls each for 4 minutes
    Then the result is:
      """
      ["reported 2 senders, 6 calls", "reported 2 senders, 6 calls"]
      """
    And each sender wrote 6 calls to "e2e.fake" and reported 2 times
    And it waited 120 seconds once

  Scenario: Once, with no minutes
    When 1 fake senders report 0 calls each for 0 minutes
    Then the result is:
      """
      ["reported 1 sender, 0 calls"]
      """
    And each sender wrote 0 calls to "e2e.fake" and reported 1 times
    And it waited 0 seconds once

  Scenario: The command writes one file for each sender to the notifier's buffer
    Given the environment sets "NOTIFIER_STORAGE_URL" to "https://storage.test"
    When the fake sender is run with "--senders 2 --calls 1"
    Then it succeeds
    And it prints:
      """
      reported 2 senders, 2 calls
      """
    And storage got 2 files under "/calls-notifier/inbox/calls/"

  Scenario: The command refuses no senders
    Given the environment sets "NOTIFIER_STORAGE_URL" to "https://storage.test"
    When the fake sender is run with "--senders 0"
    Then the exit code is 2
    And stderr mentions "--senders is at least 1"

  Scenario: The command refuses to run without storage
    Given the environment does not set "NOTIFIER_STORAGE_URL"
    When the fake sender is run with "--senders 1"
    Then the exit code is 2
    And stderr mentions "set NOTIFIER_STORAGE_URL"

  Scenario: A post's link is read from its last line
    When the link is read from "head\n<https://x.test/a|What's behind it>"
    Then the result is "https://x.test/a"

  Scenario: A post without a link on its last line has none
    When the link is read from "head\nno link here"
    Then the result is empty

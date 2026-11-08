Feature: Made-up senders, for tests

  `notifier fake-sender` reports as senders that exist only to be watched, through
  the same StorageSink every real sender writes with, into the notifier's call log
  buffer. Here storage is a fake that takes every file.

  Scenario Outline: One sender is the steady e2e; more are named by letters alone
    Then <count> senders are named "<first>" to "<last>"

    Examples:
      | count | first | last    |
      | 1     | e2e   | e2e     |
      | 3     | e2e-a | e2e-c   |
      | 28    | e2e-a | e2e-ab  |

  Scenario: Each cycle writes each sender's calls and then its report, every two minutes
    When 2 fake senders report 3 calls each for 4 minutes
    Then each sender wrote 6 calls to "e2e.fake" and reported 2 times
    And it waited 120 seconds once
    And it says "reported 2 senders, 6 calls" twice

  Scenario: Once, with no minutes
    When 1 fake senders report 0 calls each for 0 minutes
    Then each sender wrote 0 calls to "e2e.fake" and reported 1 times
    And it waited 0 seconds once

  Scenario: The command writes one file for each sender to the notifier's buffer
    When I run the fake sender with "--senders" "2" "--calls" "1"
    Then it succeeds with "reported 2 senders, 2 calls"
    And storage got 2 files under "/calls-notifier/inbox/calls/"

  Scenario Outline: The command refuses what it can't do
    When I run the fake sender with <args>, <storage>
    Then it fails with 2, saying "<message>"

    Examples:
      | args                 | storage         | message                     |
      | "--senders" "0"      | with storage    | --senders is at least 1     |
      | "--senders" "1"      | without storage | set NOTIFIER_STORAGE_URL    |

  Scenario Outline: A post's link is read from its last line
    Then the link of "<text>" is "<link>"

    Examples:
      | text                                   | link              |
      | head\n<https://x.test/a\|What's behind it> | https://x.test/a |
      | head\nno link here                     |                   |

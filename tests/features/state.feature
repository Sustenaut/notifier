Feature: What has been posted, kept in storage

  The state is a JSON file in storage's notifier tenant, named by the head
  "posted". Each save uploads a new file and moves the head to it with If-Match
  on the hash it read, or, the first time, only if the head has never moved.

  Scenario: With no head yet there is no state, and the first save makes the head
    Given storage has no head "posted"
    When the state is loaded
    Then there is no state
    When a state remembering "drops example/app" is saved
    Then the head "posted" was moved only if it had never moved
    And the head "posted" names a file holding "drops example/app"

  Scenario: A later save moves the head only if it still names what was read
    Given storage's head "posted" names a state remembering "drops example/app"
    When the state is loaded
    Then it remembers "drops example/app"
    When a state remembering "drops example/web" is saved
    Then the head "posted" was moved only if it still named what was read

Feature: Create areas

  Scenario: Successfully create an area
    When I create an area with name "Engineering"
    Then the response status is 201
    And the area name is "Engineering"

  Scenario: Create area with description
    When I create an area with name "Platform"
    Then the response status is 201
    And the area name is "Platform"

  Scenario: Cannot create area without a name
    When I create an area without a name
    Then the response status is 400
    And the error contains "name"

  Scenario: Cannot create duplicate area
    Given an area exists with name "Backend"
    When I create an area with name "Backend"
    Then the response status is 409
    And the error contains "Backend"

  Scenario: Creating an area publishes an SQS event
    When I create an area with name "Operations"
    Then the response status is 201
    And an SQS message with event "area.created" is in the HR queue

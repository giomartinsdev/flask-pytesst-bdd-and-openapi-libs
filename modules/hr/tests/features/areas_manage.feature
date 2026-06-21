Feature: Manage areas

  Scenario: List all areas
    Given an area exists with name "Engineering"
    And an area exists with name "HR"
    When I list all areas
    Then the response status is 200
    And the area count is 2

  Scenario: Get area by id
    Given an area exists with name "Engineering"
    When I get the area "Engineering"
    Then the response status is 200
    And the area name is "Engineering"

  Scenario: Update area name
    Given an area exists with name "Old Name"
    When I update area "Old Name" with name "New Name"
    Then the response status is 200
    And the area name is "New Name"

  Scenario: Assign a LEAD employee as area head
    Given an area exists with name "Engineering"
    And an employee exists with name "Alice" email "alice@corp.com" role "LEAD" salary 12000
    When I assign "alice@corp.com" as head of area "Engineering"
    Then the response status is 200
    And the area head is "alice@corp.com"
    And an SQS message with event "area.head_assigned" is in the HR queue

  Scenario: Cannot assign employee below LEAD as area head
    Given an area exists with name "Engineering"
    And an employee exists with name "Bob" email "bob@corp.com" role "JUNIOR" salary 5000
    When I assign "bob@corp.com" as head of area "Engineering"
    Then the response status is 422
    And the error contains "LEAD"

  Scenario: Cannot assign inactive employee as area head
    Given an area exists with name "Engineering"
    And an inactive employee exists with name "Carol" email "carol@corp.com" role "LEAD" salary 12000
    When I assign "carol@corp.com" as head of area "Engineering"
    Then the response status is 422
    And the error contains "inactive"

  Scenario: Delete an area with no employees
    Given an area exists with name "Empty Area"
    When I delete area "Empty Area"
    Then the response status is 204

  Scenario: Cannot delete an area that has employees
    Given an area exists with name "Engineering"
    And an employee exists with name "Alice" email "alice@corp.com" role "JUNIOR" salary 5000 in area "Engineering"
    When I delete area "Engineering"
    Then the response status is 409
    And the error contains "employees"

  Scenario: Get employees belonging to an area
    Given an area exists with name "Engineering"
    And an employee exists with name "Alice" email "alice@corp.com" role "JUNIOR" salary 5000 in area "Engineering"
    And an employee exists with name "Bob" email "bob@corp.com" role "MID" salary 7000
    When I get employees in area "Engineering"
    Then the response status is 200
    And the employee count is 1
    And the first employee name is "Alice"

Feature: Assign managers

  Scenario: Successfully assign a LEAD as manager
    Given an employee exists with name "Alice" email "alice@corp.com" role "JUNIOR" salary 5000
    And an employee exists with name "Bob" email "bob@corp.com" role "LEAD" salary 12000
    When I assign manager "bob@corp.com" to employee "alice@corp.com"
    Then the response status is 200
    And the employee manager is "bob@corp.com"

  Scenario: Cannot assign a manager below LEAD level
    Given an employee exists with name "Alice" email "alice@corp.com" role "JUNIOR" salary 5000
    And an employee exists with name "Bob" email "bob@corp.com" role "SENIOR" salary 9000
    When I assign manager "bob@corp.com" to employee "alice@corp.com"
    Then the response status is 422
    And the error contains "LEAD"

  Scenario: Cannot create circular reporting chain
    Given an employee exists with name "Alice" email "alice@corp.com" role "LEAD" salary 12000
    And an employee exists with name "Bob" email "bob@corp.com" role "LEAD" salary 12000
    And "bob@corp.com" reports to "alice@corp.com"
    When I assign manager "bob@corp.com" to employee "alice@corp.com"
    Then the response status is 422
    And the error contains "circular"

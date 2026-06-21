Feature: Deactivate employees

  Scenario: Successfully deactivate an employee with no active reports
    Given an employee exists with name "Alice" email "alice@corp.com" department "Eng" role "JUNIOR" salary 5000
    When I toggle the status of employee "alice@corp.com"
    Then the response status is 200
    And the employee is inactive

  Scenario: Cannot deactivate an employee who has active direct reports
    Given an employee exists with name "Alice" email "alice@corp.com" department "Eng" role "LEAD" salary 12000
    And an employee exists with name "Bob" email "bob@corp.com" department "Eng" role "JUNIOR" salary 5000
    And "bob@corp.com" reports to "alice@corp.com"
    When I toggle the status of employee "alice@corp.com"
    Then the response status is 422
    And the error contains "active direct reports"

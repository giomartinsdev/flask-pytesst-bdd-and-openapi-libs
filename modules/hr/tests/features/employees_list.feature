Feature: List employees

  Scenario: List all employees
    Given an employee exists with name "Alice" email "alice@corp.com" department "Engineering" role "JUNIOR" salary 5000
    And an employee exists with name "Bob" email "bob@corp.com" department "HR" role "MID" salary 7000
    When I list all employees
    Then the response status is 200
    And the employee count is 2

  Scenario: Filter employees by department
    Given an employee exists with name "Alice" email "alice@corp.com" department "Engineering" role "JUNIOR" salary 5000
    And an employee exists with name "Bob" email "bob@corp.com" department "HR" role "MID" salary 7000
    When I list employees in department "Engineering"
    Then the response status is 200
    And the employee count is 1
    And the first employee name is "Alice"

  Scenario: Filter employees by active status
    Given an employee exists with name "Alice" email "alice@corp.com" department "Engineering" role "JUNIOR" salary 5000
    And an inactive employee exists with name "Bob" email "bob@corp.com" department "HR" role "MID" salary 7000
    When I list active employees
    Then the response status is 200
    And the employee count is 1
    And the first employee name is "Alice"

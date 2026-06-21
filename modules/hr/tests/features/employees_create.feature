Feature: Hire employees

  Scenario: Successfully hire a new employee
    Given the company has no employees
    When I hire an employee with name "Alice" email "alice@corp.com" department "Engineering" role "JUNIOR" salary 5000
    Then the response status is 201
    And the employee name is "Alice"
    And the employee role is "JUNIOR"
    And the employee is active

  Scenario: Cannot hire with negative salary
    Given the company has no employees
    When I hire an employee with name "Bob" email "bob@corp.com" department "HR" role "MID" salary -100
    Then the response status is 400
    And the error contains "salary"

  Scenario: Cannot hire with duplicate email
    Given an employee exists with name "Carol" email "carol@corp.com" department "Sales" role "SENIOR" salary 8000
    When I hire an employee with name "Carol2" email "carol@corp.com" department "Sales" role "JUNIOR" salary 5000
    Then the response status is 409
    And the error contains "carol@corp.com"

  Scenario: Hiring publishes an SQS event
    Given the company has no employees
    When I hire an employee with name "Dave" email "dave@corp.com" department "Ops" role "JUNIOR" salary 4500
    Then the response status is 201
    And an SQS message with event "employee.hired" is in the HR queue

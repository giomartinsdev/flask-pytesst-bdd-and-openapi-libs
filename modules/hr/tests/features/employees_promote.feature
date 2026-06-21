Feature: Promote employees

  Scenario: Successfully promote an eligible employee
    Given an employee with name "Alice" email "alice@corp.com" role "JUNIOR" salary 5000 in role for 200 days
    When I promote employee "alice@corp.com" with salary increase 20
    Then the response status is 200
    And the employee role is "MID"
    And the employee salary increased by 20 percent from 5000

  Scenario: Cannot promote if less than 180 days in role
    Given an employee with name "Bob" email "bob@corp.com" role "JUNIOR" salary 5000 in role for 90 days
    When I promote employee "bob@corp.com" with salary increase 15
    Then the response status is 422
    And the error contains "180 days"

  Scenario: Cannot promote with salary increase below 10 percent
    Given an employee with name "Carol" email "carol@corp.com" role "MID" salary 7000 in role for 200 days
    When I promote employee "carol@corp.com" with salary increase 5
    Then the response status is 422
    And the error contains "10%"

  Scenario: Cannot promote with salary increase above 50 percent
    Given an employee with name "Dave" email "dave@corp.com" role "SENIOR" salary 9000 in role for 200 days
    When I promote employee "dave@corp.com" with salary increase 60
    Then the response status is 422
    And the error contains "50%"

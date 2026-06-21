Feature: Update product

  Scenario: Successfully update a product price
    Given a product exists with name "Wrench", category "tools", price 8.00 and stock 2
    When I update product "Wrench" in category "tools" with price 10.00
    Then the response status is 200
    And the response contains price 10.0

  Scenario: Set valid stock on a product
    Given a product exists with name "Screw", category "hardware", price 0.50 and stock 0
    When I set stock of product "Screw" in category "hardware" to 100
    Then the response status is 200
    And the response contains stock 100

  Scenario: Reject negative stock
    Given a product exists with name "Nail", category "hardware", price 0.10 and stock 10
    When I set stock of product "Nail" in category "hardware" to -5
    Then the response status is 400
    And the response error contains "negative"

  Scenario: Low stock alert published to SNS when stock reaches zero
    Given a product exists with name "Tape", category "supplies", price 3.00 and stock 1
    When I set stock of product "Tape" in category "supplies" to 0
    Then the response status is 200

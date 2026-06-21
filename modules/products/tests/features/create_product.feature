Feature: Create product

  Scenario: Successfully create a product
    Given the product catalog is empty
    When I create a product with name "Widget", category "tools", price 9.99 and stock 10
    Then the response status is 201
    And the response contains name "Widget"
    And a "product.created" event is published to SQS

  Scenario: Reject product with negative price
    Given the product catalog is empty
    When I create a product with name "Gadget", category "electronics", price -5.00 and stock 0
    Then the response status is 400
    And the response error contains "price"

  Scenario: Reject product with duplicate name in same category
    Given a product exists with name "Bolt", category "hardware", price 1.50 and stock 5
    When I create a product with name "Bolt", category "hardware", price 2.00 and stock 0
    Then the response status is 400
    And the response error contains "already exists"

  Scenario: Reject product with missing required fields
    Given the product catalog is empty
    When I create a product with missing fields
    Then the response status is 400
    And the response error contains "missing"

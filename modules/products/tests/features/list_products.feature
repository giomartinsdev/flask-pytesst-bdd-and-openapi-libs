Feature: List products

  Scenario: List all products
    Given a product exists with name "Hammer", category "tools", price 12.00 and stock 3
    And a product exists with name "Drill", category "tools", price 89.99 and stock 1
    When I list all products
    Then the response status is 200
    And the response contains 2 products

  Scenario: Filter products by category
    Given a product exists with name "Hammer", category "tools", price 12.00 and stock 3
    And a product exists with name "Phone", category "electronics", price 499.00 and stock 5
    When I list products with category "tools"
    Then the response status is 200
    And the response contains 1 products
    And the first product has name "Hammer"

  Scenario: Filter products by active status
    Given a product exists with name "Old Widget", category "tools", price 5.00 and stock 0
    And the product "Old Widget" in category "tools" is deactivated
    When I list products with active "false"
    Then the response status is 200
    And the response contains 1 products
    And the first product has name "Old Widget"

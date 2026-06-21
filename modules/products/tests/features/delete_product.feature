Feature: Delete product

  Scenario: Successfully delete a product with zero stock
    Given a product exists with name "Old Part", category "spare", price 2.00 and stock 0
    When I delete product "Old Part" in category "spare"
    Then the response status is 204
    And a "product.deleted" event is published to SQS

  Scenario: Reject deleting a product with remaining stock
    Given a product exists with name "Active Part", category "spare", price 5.00 and stock 3
    When I delete product "Active Part" in category "spare"
    Then the response status is 400
    And the response error contains "remaining stock"

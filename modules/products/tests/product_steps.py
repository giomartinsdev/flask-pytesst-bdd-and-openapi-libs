import json
import pytest
from pytest_bdd import given, when, then, parsers

from lib.assertions import (
    assert_status,
    assert_field,
    assert_error_contains,
    assert_sqs_message,
)


@pytest.fixture
def context():
    return {}


# ── Given ─────────────────────────────────────────────────────────────────────

@given("the product catalog is empty")
def catalog_is_empty():
    pass


@given(
    parsers.parse(
        'a product exists with name "{name}", category "{category}", price {price:f} and stock {stock:d}'
    )
)
def product_exists(products_bdd_client, context, name, category, price, stock):
    resp = products_bdd_client.json_post("/products", {
        "name": name, "category": category, "price": price, "stock": stock,
    })
    assert resp.status_code == 201, f"setup failed: {resp.data}"
    context.setdefault("created_ids", {})[f"{name}:{category}"] = json.loads(resp.data)["id"]


@given(parsers.parse('the product "{name}" in category "{category}" is deactivated'))
def product_deactivated(products_bdd_client, context, name, category):
    product_id = context["created_ids"][f"{name}:{category}"]
    resp = products_bdd_client.json_patch(f"/products/{product_id}/status", {})
    assert resp.status_code == 200


# ── When ──────────────────────────────────────────────────────────────────────

@when(
    parsers.parse(
        'I create a product with name "{name}", category "{category}", price {price:f} and stock {stock:d}'
    )
)
def create_product(products_bdd_client, context, name, category, price, stock):
    context["response"] = products_bdd_client.json_post("/products", {
        "name": name, "category": category, "price": price, "stock": stock,
    })


@when("I create a product with missing fields")
def create_product_missing(products_bdd_client, context):
    context["response"] = products_bdd_client.json_post("/products", {"name": "X"})


@when("I list all products")
def list_all(products_bdd_client, context):
    context["response"] = products_bdd_client.get("/products")


@when(parsers.parse('I list products with category "{category}"'))
def list_by_category(products_bdd_client, context, category):
    context["response"] = products_bdd_client.get(f"/products?category={category}")


@when(parsers.parse('I list products with active "{active}"'))
def list_by_active(products_bdd_client, context, active):
    context["response"] = products_bdd_client.get(f"/products?active={active}")


@when(parsers.parse('I update product "{name}" in category "{category}" with price {price:f}'))
def update_price(products_bdd_client, context, name, category, price):
    product_id = context["created_ids"][f"{name}:{category}"]
    context["response"] = products_bdd_client.json_put(f"/products/{product_id}", {"price": price})


@when(parsers.parse('I set stock of product "{name}" in category "{category}" to {stock:d}'))
def update_stock(products_bdd_client, context, name, category, stock):
    product_id = context["created_ids"][f"{name}:{category}"]
    context["response"] = products_bdd_client.json_patch(f"/products/{product_id}/stock", {"stock": stock})


@when(parsers.parse('I delete product "{name}" in category "{category}"'))
def delete_product(products_bdd_client, context, name, category):
    product_id = context["created_ids"][f"{name}:{category}"]
    context["response"] = products_bdd_client.delete(f"/products/{product_id}")


# ── Then ──────────────────────────────────────────────────────────────────────

@then(parsers.parse("the response status is {status:d}"))
def check_status(context, status):
    assert_status(context["response"], status)


@then(parsers.parse('the response contains name "{name}"'))
def check_name(context, name):
    assert_field(context["response"], "name", name)


@then(parsers.parse("the response contains price {price:f}"))
def check_price(context, price):
    assert_field(context["response"], "price", price)


@then(parsers.parse("the response contains stock {stock:d}"))
def check_stock(context, stock):
    assert_field(context["response"], "stock", stock)


@then(parsers.parse('the response error contains "{fragment}"'))
def check_error(context, fragment):
    assert_error_contains(context["response"], fragment)


@then(parsers.parse("the response contains {count:d} products"))
def check_count(context, count):
    body = json.loads(context["response"].data)
    assert isinstance(body, list), f"expected list, got {type(body)}"
    assert len(body) == count, f"expected {count} products, got {len(body)}"


@then(parsers.parse('the first product has name "{name}"'))
def check_first_name(context, name):
    body = json.loads(context["response"].data)
    assert body[0]["name"] == name, f"expected {name!r}, got {body[0]['name']!r}"


@then(parsers.parse('a "{event_type}" event is published to SQS'))
def check_sqs_event(products_sqs_client, products_queue_url, event_type):
    assert_sqs_message(products_sqs_client, products_queue_url, event_type)

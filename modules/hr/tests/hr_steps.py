import json
from datetime import date, timedelta

import pytest
from pytest_bdd import given, when, then, parsers

from lib.assertions import assert_status, assert_error_contains, assert_sqs_message


@pytest.fixture
def hr_context():
    return {}


# ── Given ─────────────────────────────────────────────────────────────────────

@given("the company has no employees")
def company_empty():
    pass


@given(parsers.parse('an area exists with name "{name}"'))
def area_exists(hr_bdd_client, hr_context, name):
    resp = hr_bdd_client.json_post("/areas", {"name": name})
    assert resp.status_code == 201, f"area setup failed: {resp.data}"
    hr_context.setdefault("areas", {})[name] = json.loads(resp.data)


@given(
    parsers.parse(
        'an employee exists with name "{name}" email "{email}" role "{role}" salary {salary:g}'
    )
)
def employee_exists(hr_bdd_client, hr_context, name, email, role, salary):
    resp = hr_bdd_client.json_post("/employees", {
        "name": name, "email": email, "role": role, "salary": salary,
    })
    assert resp.status_code == 201, f"setup failed: {resp.data}"
    hr_context.setdefault("employees", {})[email] = json.loads(resp.data)


@given(
    parsers.parse(
        'an employee exists with name "{name}" email "{email}" role "{role}" salary {salary:g} in area "{area_name}"'
    )
)
def employee_exists_in_area(hr_bdd_client, hr_context, name, email, role, salary, area_name):
    area = hr_context.get("areas", {}).get(area_name)
    assert area is not None, f"area {area_name!r} must be created before this step"
    resp = hr_bdd_client.json_post("/employees", {
        "name": name, "email": email, "role": role, "salary": salary,
        "area_id": area["id"],
    })
    assert resp.status_code == 201, f"setup failed: {resp.data}"
    hr_context.setdefault("employees", {})[email] = json.loads(resp.data)


@given(
    parsers.parse(
        'an inactive employee exists with name "{name}" email "{email}" role "{role}" salary {salary:g}'
    )
)
def inactive_employee_exists(hr_bdd_client, hr_context, name, email, role, salary):
    resp = hr_bdd_client.json_post("/employees", {
        "name": name, "email": email, "role": role, "salary": salary,
    })
    assert resp.status_code == 201, f"setup failed: {resp.data}"
    emp = json.loads(resp.data)
    hr_context.setdefault("employees", {})[email] = emp
    toggle = hr_bdd_client.json_patch(f"/employees/{emp['id']}/status", {})
    assert toggle.status_code == 200, f"toggle failed: {toggle.data}"
    hr_context["employees"][email] = json.loads(toggle.data)


@given(
    parsers.parse(
        'an employee with name "{name}" email "{email}" role "{role}" salary {salary:g} in role for {days:d} days'
    )
)
def employee_with_role_since(hr_bdd_client, hr_context, name, email, role, salary, days):
    role_since = (date.today() - timedelta(days=days)).isoformat()
    resp = hr_bdd_client.json_post("/employees", {
        "name": name, "email": email, "role": role, "salary": salary,
        "hire_date": role_since, "role_since": role_since,
    })
    assert resp.status_code == 201, f"setup failed: {resp.data}"
    hr_context.setdefault("employees", {})[email] = json.loads(resp.data)


@given(parsers.parse('"{reporter_email}" reports to "{manager_email}"'))
def assign_reports_to(hr_bdd_client, hr_context, reporter_email, manager_email):
    reporter = hr_context["employees"][reporter_email]
    manager = hr_context["employees"][manager_email]
    resp = hr_bdd_client.json_post(f"/employees/{reporter['id']}/manager", {"manager_id": manager["id"]})
    assert resp.status_code == 200, f"assign manager failed: {resp.data}"
    hr_context["employees"][reporter_email] = json.loads(resp.data)


# ── When — employees ──────────────────────────────────────────────────────────

@when(
    parsers.parse(
        'I hire an employee with name "{name}" email "{email}" role "{role}" salary {salary:g}'
    )
)
def hire_employee(hr_bdd_client, hr_context, name, email, role, salary):
    hr_context["response"] = hr_bdd_client.json_post("/employees", {
        "name": name, "email": email, "role": role, "salary": salary,
    })
    if hr_context["response"].status_code == 201:
        hr_context.setdefault("employees", {})[email] = json.loads(hr_context["response"].data)


@when("I list all employees")
def list_all_employees(hr_bdd_client, hr_context):
    hr_context["response"] = hr_bdd_client.get("/employees")


@when(parsers.parse('I list employees in area "{area_name}"'))
def list_by_area(hr_bdd_client, hr_context, area_name):
    area = hr_context.get("areas", {}).get(area_name)
    assert area is not None
    hr_context["response"] = hr_bdd_client.get(f"/employees?area_id={area['id']}")


@when("I list active employees")
def list_active(hr_bdd_client, hr_context):
    hr_context["response"] = hr_bdd_client.get("/employees?active=true")


@when(parsers.parse('I promote employee "{email}" with salary increase {pct:g}'))
def promote_employee(hr_bdd_client, hr_context, email, pct):
    emp = hr_context["employees"][email]
    hr_context["response"] = hr_bdd_client.json_post(
        f"/employees/{emp['id']}/promote", {"salary_increase_pct": pct}
    )


@when(parsers.parse('I assign manager "{manager_email}" to employee "{emp_email}"'))
def do_assign_manager(hr_bdd_client, hr_context, manager_email, emp_email):
    emp = hr_context["employees"][emp_email]
    manager = hr_context["employees"][manager_email]
    hr_context["response"] = hr_bdd_client.json_post(
        f"/employees/{emp['id']}/manager", {"manager_id": manager["id"]}
    )


@when(parsers.parse('I toggle the status of employee "{email}"'))
def toggle_status(hr_bdd_client, hr_context, email):
    emp = hr_context["employees"][email]
    hr_context["response"] = hr_bdd_client.json_patch(f"/employees/{emp['id']}/status", {})


@when(parsers.parse('I assign employee "{email}" to area "{area_name}"'))
def assign_employee_to_area(hr_bdd_client, hr_context, email, area_name):
    emp = hr_context["employees"][email]
    area = hr_context.get("areas", {}).get(area_name)
    assert area is not None
    hr_context["response"] = hr_bdd_client.json_patch(
        f"/employees/{emp['id']}/area", {"area_id": area["id"]}
    )
    if hr_context["response"].status_code == 200:
        hr_context["employees"][email] = json.loads(hr_context["response"].data)


# ── When — areas ──────────────────────────────────────────────────────────────

@when(parsers.parse('I create an area with name "{name}"'))
def create_area(hr_bdd_client, hr_context, name):
    hr_context["response"] = hr_bdd_client.json_post("/areas", {"name": name})
    if hr_context["response"].status_code == 201:
        hr_context.setdefault("areas", {})[name] = json.loads(hr_context["response"].data)


@when("I create an area without a name")
def create_area_no_name(hr_bdd_client, hr_context):
    hr_context["response"] = hr_bdd_client.json_post("/areas", {})


@when("I list all areas")
def list_all_areas(hr_bdd_client, hr_context):
    hr_context["response"] = hr_bdd_client.get("/areas")


@when(parsers.parse('I get the area "{name}"'))
def get_area_by_name(hr_bdd_client, hr_context, name):
    area = hr_context.get("areas", {}).get(name)
    assert area is not None
    hr_context["response"] = hr_bdd_client.get(f"/areas/{area['id']}")


@when(parsers.parse('I update area "{name}" with name "{new_name}"'))
def update_area(hr_bdd_client, hr_context, name, new_name):
    area = hr_context.get("areas", {}).get(name)
    assert area is not None
    hr_context["response"] = hr_bdd_client.json_put(f"/areas/{area['id']}", {"name": new_name})
    if hr_context["response"].status_code == 200:
        hr_context.setdefault("areas", {})[new_name] = json.loads(hr_context["response"].data)


@when(parsers.parse('I assign "{email}" as head of area "{area_name}"'))
def assign_area_head(hr_bdd_client, hr_context, email, area_name):
    emp = hr_context["employees"][email]
    area = hr_context.get("areas", {}).get(area_name)
    assert area is not None
    hr_context["response"] = hr_bdd_client.json_patch(
        f"/areas/{area['id']}/head", {"head_employee_id": emp["id"]}
    )
    if hr_context["response"].status_code == 200:
        hr_context["areas"][area_name] = json.loads(hr_context["response"].data)


@when(parsers.parse('I delete area "{name}"'))
def delete_area(hr_bdd_client, hr_context, name):
    area = hr_context.get("areas", {}).get(name)
    assert area is not None
    hr_context["response"] = hr_bdd_client.delete(f"/areas/{area['id']}")


@when(parsers.parse('I get employees in area "{area_name}"'))
def get_area_employees(hr_bdd_client, hr_context, area_name):
    area = hr_context.get("areas", {}).get(area_name)
    assert area is not None
    hr_context["response"] = hr_bdd_client.get(f"/areas/{area['id']}/employees")


# ── Then ──────────────────────────────────────────────────────────────────────

@then(parsers.parse("the response status is {status:d}"))
def check_hr_status(hr_context, status):
    assert_status(hr_context["response"], status)


@then(parsers.parse('the employee name is "{name}"'))
def check_employee_name(hr_context, name):
    body = json.loads(hr_context["response"].data)
    assert body.get("name") == name, f"expected name={name!r}, got {body.get('name')!r}"


@then(parsers.parse('the employee role is "{role}"'))
def check_employee_role(hr_context, role):
    body = json.loads(hr_context["response"].data)
    assert body.get("role") == role, f"expected role={role!r}, got {body.get('role')!r}"


@then("the employee is active")
def check_employee_active(hr_context):
    body = json.loads(hr_context["response"].data)
    assert body.get("active") is True, f"expected active=True, got {body.get('active')!r}"


@then("the employee is inactive")
def check_employee_inactive(hr_context):
    body = json.loads(hr_context["response"].data)
    assert body.get("active") is False, f"expected active=False, got {body.get('active')!r}"


@then(parsers.parse('the error contains "{fragment}"'))
def check_hr_error(hr_context, fragment):
    assert_error_contains(hr_context["response"], fragment)


@then(parsers.parse("the employee count is {count:d}"))
def check_employee_count(hr_context, count):
    body = json.loads(hr_context["response"].data)
    assert isinstance(body, list), f"expected list, got {type(body)}"
    assert len(body) == count, f"expected {count} employees, got {len(body)}"


@then(parsers.parse('the first employee name is "{name}"'))
def check_first_employee_name(hr_context, name):
    body = json.loads(hr_context["response"].data)
    assert body[0]["name"] == name, f"expected {name!r}, got {body[0]['name']!r}"


@then(parsers.parse('the employee salary increased by {pct:g} percent from {original:g}'))
def check_salary_increase(hr_context, pct, original):
    body = json.loads(hr_context["response"].data)
    expected = original * (1 + pct / 100)
    actual = body.get("salary")
    assert abs(actual - expected) < 0.01, f"expected salary ~{expected:.2f}, got {actual}"


@then(parsers.parse('the employee manager is "{manager_email}"'))
def check_manager(hr_context, manager_email):
    manager = hr_context["employees"][manager_email]
    body = json.loads(hr_context["response"].data)
    assert body.get("manager_id") == manager["id"], (
        f"expected manager_id={manager['id']}, got {body.get('manager_id')}"
    )


@then(parsers.parse('the employee area is "{area_name}"'))
def check_employee_area(hr_context, area_name):
    area = hr_context.get("areas", {}).get(area_name)
    assert area is not None
    body = json.loads(hr_context["response"].data)
    assert body.get("area_id") == area["id"], (
        f"expected area_id={area['id']}, got {body.get('area_id')}"
    )


@then(parsers.parse('an SQS message with event "{event_type}" is in the HR queue'))
def check_hr_sqs_event(hr_sqs_client, hr_queue_url, event_type):
    assert_sqs_message(hr_sqs_client, hr_queue_url, event_type)


@then(parsers.parse('the area name is "{name}"'))
def check_area_name(hr_context, name):
    body = json.loads(hr_context["response"].data)
    assert body.get("name") == name, f"expected name={name!r}, got {body.get('name')!r}"


@then(parsers.parse("the area count is {count:d}"))
def check_area_count(hr_context, count):
    body = json.loads(hr_context["response"].data)
    assert isinstance(body, list), f"expected list, got {type(body)}"
    assert len(body) == count, f"expected {count} areas, got {len(body)}"


@then(parsers.parse('the area head is "{email}"'))
def check_area_head(hr_context, email):
    emp = hr_context["employees"][email]
    body = json.loads(hr_context["response"].data)
    assert body.get("head_employee_id") == emp["id"], (
        f"expected head_employee_id={emp['id']}, got {body.get('head_employee_id')}"
    )

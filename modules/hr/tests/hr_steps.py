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


@given(
    parsers.parse(
        'an employee exists with name "{name}" email "{email}" department "{dept}" role "{role}" salary {salary:g}'
    )
)
def employee_exists(hr_bdd_client, hr_context, name, email, dept, role, salary):
    resp = hr_bdd_client.json_post("/employees", {
        "name": name, "email": email, "department": dept, "role": role, "salary": salary,
    })
    assert resp.status_code == 201, f"setup failed: {resp.data}"
    hr_context.setdefault("employees", {})[email] = json.loads(resp.data)


@given(
    parsers.parse(
        'an inactive employee exists with name "{name}" email "{email}" department "{dept}" role "{role}" salary {salary:g}'
    )
)
def inactive_employee_exists(hr_bdd_client, hr_context, name, email, dept, role, salary):
    resp = hr_bdd_client.json_post("/employees", {
        "name": name, "email": email, "department": dept, "role": role, "salary": salary,
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
        "name": name, "email": email, "department": "Engineering",
        "role": role, "salary": salary,
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


# ── When ──────────────────────────────────────────────────────────────────────

@when(
    parsers.parse(
        'I hire an employee with name "{name}" email "{email}" department "{dept}" role "{role}" salary {salary:g}'
    )
)
def hire_employee(hr_bdd_client, hr_context, name, email, dept, role, salary):
    hr_context["response"] = hr_bdd_client.json_post("/employees", {
        "name": name, "email": email, "department": dept, "role": role, "salary": salary,
    })
    if hr_context["response"].status_code == 201:
        hr_context.setdefault("employees", {})[email] = json.loads(hr_context["response"].data)


@when("I list all employees")
def list_all_employees(hr_bdd_client, hr_context):
    hr_context["response"] = hr_bdd_client.get("/employees")


@when(parsers.parse('I list employees in department "{dept}"'))
def list_by_department(hr_bdd_client, hr_context, dept):
    hr_context["response"] = hr_bdd_client.get(f"/employees?department={dept}")


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
def check_manager(hr_bdd_client, hr_context, manager_email):
    manager = hr_context["employees"][manager_email]
    body = json.loads(hr_context["response"].data)
    assert body.get("manager_id") == manager["id"], (
        f"expected manager_id={manager['id']}, got {body.get('manager_id')}"
    )


@then(parsers.parse('an SQS message with event "{event_type}" is in the HR queue'))
def check_hr_sqs_event(hr_sqs_client, hr_queue_url, event_type):
    assert_sqs_message(hr_sqs_client, hr_queue_url, event_type)

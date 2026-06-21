# Migration Guide — Flask + pytest → BDD with Containers + OpenAPI

This document is written for an AI agent performing a migration.
Follow every rule exactly. Do not guess; if a case is not covered here, re-read the source files listed in each section.

---

## Stack overview

Two in-repo shared libraries drive everything:

| Library | Path | Purpose |
|---|---|---|
| `pytest-bdd-utils` | `modules/lib/pytest-bdd-utils/lib/` | Real-infra BDD fixtures (containers, SQS, S3, truncation) |
| `openapi-flask-utils` | `modules/lib/openapi-flask-utils/lib/` | `@schema()` decorator + Swagger UI route |

Source for any Flask module lives under `modules/<name>/src/<name>/`.
Tests live under `modules/<name>/tests/`.

---

## Part 1 — Migrate pytest to pytest-bdd with integration containers

### 1.1 Module layout

```
modules/<name>/
├── src/<name>/
│   ├── app.py              # create_app() factory
│   ├── db.py               # SQLAlchemy Base
│   └── ...
└── tests/
    ├── conftest.py         # infra + Flask wiring
    ├── <name>_steps.py     # all Given/When/Then step functions
    ├── features/
    │   ├── thing_create.feature
    │   └── thing_manage.feature
    ├── test_thing_create.py
    └── test_thing_manage.py
```

### 1.2 conftest.py

This is the most critical file. It must:

1. **Add all paths to `sys.path`** so both the module source and the shared libraries are importable.
2. **Declare a `BDDConfig`** fixture (session-scoped) that specifies which DB, queues, topics, and buckets are needed.
3. **Declare a `BDDInfra`** fixture (session-scoped) that starts containers once per test session.
4. **Declare a `_reset`** fixture (function-scoped, `autouse=True`) that truncates tables and drains queues before every test.
5. **Declare a Flask app fixture** that wires the test infra DB session into the app's service layer.
6. **Declare a `bdd_client`** fixture (function-scoped) that wraps the Flask test client in `BDDClient`.
7. **Import all steps** via `from <name>_steps import *`.

**Exact template** (adapt names):

```python
import sys, os

_tests   = os.path.dirname(os.path.abspath(__file__))
_src     = os.path.abspath(os.path.join(_tests, "..", "src"))
_lib     = os.path.abspath(os.path.join(_tests, "..", "..", "lib"))
_bdd     = os.path.join(_lib, "pytest-bdd-utils")
_openapi = os.path.join(_lib, "openapi-flask-utils")

for _p in (_src, _bdd, _openapi, _tests):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
from lib.config import BDDConfig
from lib.infra  import BDDInfra
from lib.client import BDDClient

from <name>_steps import *  # noqa: F401,F403

from <name>.app import create_app
from <name>.db  import Base
from <name>.application.<name>_service import <Name>ApplicationService
from <name>.domain.<entity>.repository import <Entity>Repository
import <name>.api.<entity>.blueprint as bp_module

_QUEUE = "<name>-events"
_TOPIC = "<name>-alerts"


@pytest.fixture(scope="session")
def _<name>_config():
    return BDDConfig.from_env(
        db_base=Base,
        db_type="sqlserver",          # or "postgres"
        sqs_queues=[_QUEUE],
        sns_topics=[_TOPIC],
    )


@pytest.fixture(scope="session")
def _<name>_infra(_<name>_config):
    infra = BDDInfra.from_config(_<name>_config)
    yield infra
    infra.stop()


@pytest.fixture
def <name>_sqs_client(_<name>_infra):
    return _<name>_infra.sqs


@pytest.fixture
def <name>_queue_url(_<name>_infra):
    return _<name>_infra.queue_urls[_QUEUE]


@pytest.fixture(autouse=True)
def _<name>_reset(_<name>_infra):
    # List tables in dependency order: children first, then parents.
    # For circular FKs, order does not matter — the infra handles them.
    _<name>_infra.truncate_tables("child_table", "parent_table")
    _<name>_infra.drain_all_queues()
    yield
    _<name>_infra.drain_all_queues()


@pytest.fixture
def _<name>_flask(_<name>_infra):
    app = create_app(db_url=_<name>_infra.db_url)
    app.config["TESTING"] = True
    _sessions = []

    from <name>.application.event_bus import EventBus

    def _make_bus():
        return EventBus(
            sqs_client=_<name>_infra.sqs,
            sns_client=_<name>_infra.sns,
            queue_url=_<name>_infra.queue_urls[_QUEUE],
            topic_arn=_<name>_infra.topic_arns[_TOPIC],
        )

    def _patched_service():
        s = _<name>_infra.make_session()
        _sessions.append(s)
        return <Name>ApplicationService(
            <entity>_repo=<Entity>Repository(s),
            event_bus=_make_bus(),
        )

    @app.teardown_request
    def _cleanup(_=None):
        for s in _sessions:
            s.close()
        _sessions.clear()

    bp_module._make_service = _patched_service
    return app


@pytest.fixture
def <name>_bdd_client(_<name>_flask):
    with _<name>_flask.test_client() as raw:
        yield BDDClient(raw)
```

**Rules:**
- Always prefix fixture names with the module name (e.g. `hr_bdd_client`, `hr_queue_url`). This prevents collisions when multiple modules share a single pytest session.
- Session-scoped fixtures start containers once. Never make DB/AWS fixtures function-scoped.
- The `_patched_service` closure captures `_sessions` so the session opened per-request is closed after each request, preventing connection leaks.
- `bp_module._make_service` is monkey-patched to inject the test session. The blueprint's `_make_service` function must be a module-level callable (not a class method or lambda) for this to work.

### 1.3 BDDConfig reference

```python
BDDConfig.from_env(
    db_base=Base,                      # SQLAlchemy declarative base
    db_type="postgres",                # "postgres" | "sqlserver"
    sqs_queues=["queue-name"],         # created in LocalStack automatically
    sns_topics=["topic-name"],         # created in LocalStack automatically
    s3_buckets=["bucket-name"],        # created in LocalStack automatically
)
```

`from_env` reads `DATABASE_URL` and `AWS_ENDPOINT_URL` from environment. When those vars are absent, `BDDInfra.from_config` spins up testcontainers (Docker must be running).

For SQL Server use `db_type="sqlserver"` and ensure the image `flask-bdd-mssql:latest` is built:
```
modules/lib/mssql/Dockerfile
```

For Postgres the image `postgres:16-alpine` is pulled from Docker Hub automatically.

### 1.4 Feature files

Place every `.feature` file under `tests/features/`. Use the Gherkin `Feature` / `Scenario` / `Given` / `When` / `Then` / `And` keywords.

**Naming rules:**
- One feature file per logical group of operations (e.g. `employees_create.feature`, `employees_promote.feature`).
- Step text must match the `@given`, `@when`, `@then` decorators in the steps file **exactly** (case-sensitive).
- Use `parsers.parse(...)` for any step with captured values. Use `{name}` for strings, `{count:d}` for ints, `{salary:g}` for floats.

**Minimal example:**

```gherkin
Feature: Create things

  Scenario: Successfully create a thing
    Given no things exist
    When I create a thing with name "Widget"
    Then the response status is 201
    And the thing name is "Widget"

  Scenario: Cannot create a duplicate thing
    Given a thing exists with name "Gadget"
    When I create a thing with name "Gadget"
    Then the response status is 409
    And the error contains "Gadget"

  Scenario: Creating a thing publishes an SQS event
    When I create a thing with name "Doohickey"
    Then the response status is 201
    And an SQS message with event "thing.created" is in the queue
```

### 1.5 Step definitions

All steps for a module live in one file: `tests/<name>_steps.py`.

**Structure:**

```python
import json
import pytest
from pytest_bdd import given, when, then, parsers
from lib.assertions import assert_status, assert_error_contains, assert_sqs_message


@pytest.fixture
def <name>_context():
    return {}


# ── Given ─────────────────────────────────────────────────────────────────────

@given("no things exist")
def things_empty():
    pass                                    # reset_between_tests handles cleanup


@given(parsers.parse('a thing exists with name "{name}"'))
def thing_exists(<name>_bdd_client, <name>_context, name):
    resp = <name>_bdd_client.json_post("/things", {"name": name})
    assert resp.status_code == 201, f"setup failed: {resp.data}"
    <name>_context.setdefault("things", {})[name] = json.loads(resp.data)


# ── When ──────────────────────────────────────────────────────────────────────

@when(parsers.parse('I create a thing with name "{name}"'))
def create_thing(<name>_bdd_client, <name>_context, name):
    <name>_context["response"] = <name>_bdd_client.json_post("/things", {"name": name})
    if <name>_context["response"].status_code == 201:
        body = json.loads(<name>_context["response"].data)
        <name>_context.setdefault("things", {})[name] = body


@when("I list all things")
def list_things(<name>_bdd_client, <name>_context):
    <name>_context["response"] = <name>_bdd_client.get("/things")


# ── Then ──────────────────────────────────────────────────────────────────────

@then(parsers.parse("the response status is {status:d}"))
def check_status(<name>_context, status):
    assert_status(<name>_context["response"], status)


@then(parsers.parse('the thing name is "{name}"'))
def check_name(<name>_context, name):
    body = json.loads(<name>_context["response"].data)
    assert body.get("name") == name, f"expected name={name!r}, got {body.get('name')!r}"


@then(parsers.parse('the error contains "{fragment}"'))
def check_error(<name>_context, fragment):
    assert_error_contains(<name>_context["response"], fragment)


@then(parsers.parse('an SQS message with event "{event_type}" is in the queue'))
def check_sqs(<name>_sqs_client, <name>_queue_url, event_type):
    assert_sqs_message(<name>_sqs_client, <name>_queue_url, event_type)
```

**Rules:**
- The `<name>_context` fixture is a plain `dict` that accumulates state across steps in a single scenario. It holds `"response"` (the last HTTP response) and lookup dicts like `"things"` or `"employees"`.
- Step function parameter names must exactly match fixture names. If a parameter does not match a fixture, pytest-bdd raises a confusing error.
- Given steps that set up preconditions should call the real HTTP API (not the service layer directly) so that those setups also exercise the route.
- When a Given step creates a resource that a later step references by name, store it in `<name>_context["things"][name]`.

### 1.6 Test runner files

One file per `.feature` file. Contains only:

```python
# tests/test_thing_create.py
from pathlib import Path
from pytest_bdd import scenarios

scenarios(str(Path(__file__).parent / "features" / "thing_create.feature"))
```

No test functions. `scenarios()` generates one test per Scenario block.

### 1.7 BDDClient reference

```python
client.get(path)                      # GET
client.json_post(path, body_dict)     # POST  application/json
client.json_put(path, body_dict)      # PUT   application/json
client.json_patch(path, body_dict)    # PATCH application/json
client.delete(path)                   # DELETE
```

Returns the raw Flask `TestResponse`. Access `.status_code` and `.data`.

### 1.8 Assertions reference

```python
from lib.assertions import assert_status, assert_field, assert_error_contains, assert_sqs_message, assert_s3_object_exists

assert_status(response, 201)
assert_field(response, "name", "Widget")
assert_error_contains(response, "duplicate")
assert_sqs_message(sqs_client, queue_url, "thing.created")   # polls up to 10×
assert_s3_object_exists(s3_client, "bucket", "some/key.txt")
```

### 1.9 Table truncation

Call `infra.truncate_tables(*table_names)` in the `autouse` reset fixture.

- **Postgres**: uses `TRUNCATE ... RESTART IDENTITY CASCADE`.
- **SQL Server**: disables all FK constraints (outgoing and incoming) for the listed tables, deletes all rows, reseeds identity columns, re-enables constraints. This handles circular FKs automatically.
- Pass table names in any order for SQL Server. For Postgres, pass children before parents.

### 1.10 Blueprint service injection

The blueprint must expose a module-level `_make_service` function (not a method):

```python
# in the blueprint file
def _make_service() -> ThingService:
    session = current_app.config["SESSION_FACTORY"]()
    ...
    return ThingService(repo=ThingRepository(session), event_bus=...)
```

In `conftest.py` replace it per test:

```python
import <name>.api.<entity>.blueprint as bp_module

def _patched():
    s = infra.make_session()
    _sessions.append(s)
    return ThingService(repo=ThingRepository(s), event_bus=_make_bus())

bp_module._make_service = _patched
```

This is the standard injection pattern. Do not introduce ABC, DI containers, or `unittest.mock`.

---

## Part 2 — Add OpenAPI and Swagger UI

### 2.1 Install the route

In `create_app()`:

```python
from lib.openapi import install_openapi_route

def create_app(...) -> Flask:
    app = Flask(__name__)
    ...
    app.register_blueprint(things_bp)
    install_openapi_route(app, title="Things API", version="0.1.0")
    return app
```

This registers two routes:
- `GET /openapi.json` — lazy-built OpenAPI 3.0.3 spec (built on first request).
- `GET /docs` — Swagger UI with dark/light mode toggle, shadcn-inspired design.

Parameters:
```python
install_openapi_route(
    app,
    title="My API",        # shown in Swagger UI header and spec info.title
    version="1.0.0",       # spec info.version
    jwt=True,              # adds BearerAuth scheme + Authorize button (default True)
)
```

### 2.2 The @schema() decorator

Apply to every route handler **before** Flask's route decorator (i.e. immediately after `@bp.post(...)`):

```python
from lib.openapi import schema

@things_bp.post("")
@schema(request=CreateThingRequest, response=Thing, status=201)
def create():
    ...

@things_bp.get("")
@schema(query=ThingFilters, response=Thing, many=True)
def list_things():
    ...

@things_bp.get("/<int:tid>")
@schema(response=Thing)
def get_thing(tid: int):
    ...

@things_bp.delete("/<int:tid>")
@schema(status=204)
def delete_thing(tid: int):
    ...
```

All parameters are keyword-only:

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `request` | dataclass | `None` | JSON request body schema |
| `query` | dataclass | `None` | Query-string parameters |
| `response` | dataclass or SQLAlchemy model | `None` | Response body schema |
| `many` | `bool` | `False` | Wrap response schema in `{"type": "array", "items": ...}` |
| `status` | `int` | `200` | Success HTTP status code emitted in the spec |

### 2.3 Request/response schemas

Define a `schemas.py` file in the API layer (not the domain layer):

```python
# src/<name>/api/<entity>/schemas.py
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class CreateThingRequest:
    name: str                     # required — no default, not Optional
    price: float                  # required
    category: Optional[str] = None   # optional — has default


@dataclass
class UpdateThingRequest:
    name: Optional[str] = None
    price: Optional[float] = None


@dataclass
class ThingFilters:              # used with query=
    category: Optional[str] = None
    active: Optional[bool] = None
```

**Rules for required vs optional fields:**
- A field is marked `required` in the generated spec when it has **no** default value and its type is **not** `Optional[X]`.
- Use `Optional[X]` (i.e. `Union[X, None]`) for any field the caller may omit.
- Never use `field(default=...)` in API-layer schemas; keep them plain dataclasses.

### 2.4 How schemas are converted

`_annotation_to_schema` maps Python types to JSON Schema:

| Python type | JSON Schema |
|---|---|
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `datetime.date` | `{"type": "string", "format": "date"}` |
| `datetime.datetime` | `{"type": "string", "format": "date-time"}` |
| `Optional[X]` | same as `X` (nullability expressed via `required` list, not `nullable`) |
| `list[X]` / `List[X]` | `{"type": "array", "items": <X schema>}` |
| `enum.Enum` subclass | `{"type": "string", "enum": [values...]}` |
| anything else | `{"type": "string"}` |

SQLAlchemy model columns are converted via `model_to_schema()` which inspects column types. Both approaches produce a `$ref` in `components/schemas`.

### 2.5 Blueprint tags

OpenAPI operations are grouped by blueprint name. The tag is derived from the Flask endpoint:
`"employees.hire"` → tag `"employees"`.

Blueprints appear as collapsible sections in Swagger UI automatically. No manual tag configuration needed.

### 2.6 Security

When `jwt=True` (default), the spec includes:

```json
{
  "components": {
    "securitySchemes": {
      "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }
  },
  "security": [{"BearerAuth": []}]
}
```

The Authorize button in Swagger UI is enabled. Pass `jwt=False` to suppress both.

---

## Common pitfalls and rules

### `from __future__ import annotations` is required when a class has a method named `list`

Python evaluates `list[Employee]` as a return annotation at class definition time. If the class defines a method called `list`, the name `list` resolves to the method, causing `TypeError: 'function' object is not subscriptable`.

Fix: add `from __future__ import annotations` at the top of any file containing a class with both a method named `list` and `list[X]` return annotations. This applies to repositories and application services.

```python
# REQUIRED in repository.py and any service with a .list() method
from __future__ import annotations
```

### Circular FK between two tables (SQLAlchemy DDL)

When table A has a FK to B and B has a FK to A, SQLAlchemy cannot emit both `CREATE TABLE` statements cleanly. Fix: add `use_alter=True` and a `name=` on the FK that creates the cycle:

```python
# In the model that holds the "weaker" FK
area_id = Column(
    Integer,
    ForeignKey("areas.id", use_alter=True, name="fk_employee_area"),
    nullable=True,
)
```

This defers the FK to an `ALTER TABLE` after both tables exist.

### Fixture namespace collision in sibling conftest files

Sibling `conftest.py` files in the same pytest session share the fixture namespace. If two conftests define a fixture with the same name (e.g. `bdd_client`), one silently overrides the other.

Rule: prefix every fixture with the module name: `hr_bdd_client`, `products_bdd_client`, `hr_context`, `products_context`. Never use generic names like `client`, `context`, or `app` in a module conftest.

### The reset fixture must be autouse at function scope

```python
@pytest.fixture(autouse=True)              # runs before every test
def _<name>_reset(_<name>_infra):
    _<name>_infra.truncate_tables(...)     # clean state BEFORE the test
    _<name>_infra.drain_all_queues()
    yield
    _<name>_infra.drain_all_queues()       # clean queues AFTER (avoid SQS bleed-through)
```

Do not use `scope="session"` here. Do not truncate inside a Given step — the autouse fixture handles it.

### No mocks

All tests hit real infrastructure: a real database container and a real LocalStack container. Do not use `unittest.mock`, `MagicMock`, or `@patch`. The only patching allowed is replacing `bp_module._make_service` to inject the test DB session.

### EventBus publishing in tests

The `EventBus` in tests must receive the actual LocalStack SQS/SNS clients from `_infra`. The `_make_bus()` closure in conftest wires this:

```python
def _make_bus():
    return EventBus(
        sqs_client=infra.sqs,
        sns_client=infra.sns,
        queue_url=infra.queue_urls["my-queue"],
        topic_arn=infra.topic_arns["my-topic"],
    )
```

`assert_sqs_message` polls LocalStack SQS directly to verify events published by the route handler.

### `scenarios()` in test runner files

```python
from pytest_bdd import scenarios
from pathlib import Path

scenarios(str(Path(__file__).parent / "features" / "thing_create.feature"))
```

Use an absolute path constructed with `Path(__file__).parent`. Do not rely on `pytest.ini`'s `bdd_features_base_dir` — it breaks when test files are run in isolation.

---

## Migration checklist

Use this list when migrating an existing Flask module.

### BDD layer

- [ ] Create `tests/` directory with `__init__.py` (empty).
- [ ] Write `tests/conftest.py` following the template in §1.2. Prefix all fixtures with module name.
- [ ] Write `tests/<name>_steps.py`. Define `<name>_context` fixture. Group steps by Given / When / Then.
- [ ] Write feature files under `tests/features/`. One `.feature` per logical group.
- [ ] Write `tests/test_<feature>.py` for each feature file. Contents: `scenarios(...)` only.
- [ ] Confirm that `create_app(db_url=...)` accepts an override URL.
- [ ] Confirm that each blueprint exposes a module-level `_make_service()` function.
- [ ] Confirm `app.config["SESSION_FACTORY"]` is set in `create_app()`.
- [ ] Add `from __future__ import annotations` to any repository or service file with a `list` method.
- [ ] Add `use_alter=True` to any FK that creates a circular DDL dependency.
- [ ] Ensure Docker is running before starting tests.

### OpenAPI layer

- [ ] Create `src/<name>/api/<entity>/schemas.py` with dataclass request/filter types.
- [ ] Add `@schema(...)` to every blueprint route handler.
- [ ] Call `install_openapi_route(app, title=..., version=...)` at the end of `create_app()`, after all `register_blueprint()` calls.
- [ ] Verify `/openapi.json` returns valid JSON after startup.
- [ ] Verify `/docs` renders the Swagger UI.
- [ ] Confirm each blueprint appears as a separate tag section in the UI.
- [ ] Confirm required fields are marked in the spec (no `Optional`, no default value).

---

## File index

| File | Role |
|---|---|
| `modules/lib/pytest-bdd-utils/lib/config.py` | `BDDConfig` dataclass |
| `modules/lib/pytest-bdd-utils/lib/infra.py` | `BDDInfra` — container lifecycle, truncation, AWS clients |
| `modules/lib/pytest-bdd-utils/lib/fixtures.py` | Base pytest fixtures (`bdd_infra`, `bdd_client`, `reset_between_tests`) |
| `modules/lib/pytest-bdd-utils/lib/client.py` | `BDDClient` — JSON-aware HTTP test client |
| `modules/lib/pytest-bdd-utils/lib/assertions.py` | `assert_status`, `assert_field`, `assert_error_contains`, `assert_sqs_message`, `assert_s3_object_exists` |
| `modules/lib/openapi-flask-utils/lib/openapi.py` | `schema()` decorator, `build_spec()`, `install_openapi_route()` |
| `modules/lib/openapi-flask-utils/lib/swagger_ui.html` | Swagger UI HTML template (shadcn-styled, dark/light toggle) |
| `modules/hr/tests/conftest.py` | Reference implementation of the conftest pattern |
| `modules/hr/tests/hr_steps.py` | Reference implementation of step definitions |
| `modules/hr/tests/features/employees_create.feature` | Reference feature file |
| `modules/hr/src/hr/api/employees/blueprint.py` | Reference blueprint with `@schema()` and `_make_service` |
| `modules/hr/src/hr/api/employees/schemas.py` | Reference API-layer schema dataclasses |
| `modules/hr/src/hr/app.py` | Reference `create_app()` with `install_openapi_route` |

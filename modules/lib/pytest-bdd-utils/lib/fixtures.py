from collections.abc import Generator

import pytest

from lib.client import BDDClient
from lib.infra import BDDInfra

# ── Infrastructure (session-scoped — containers start once per test session) ──


@pytest.fixture(scope="session")
def bdd_infra(bdd_config) -> Generator[BDDInfra, None, None]:
    infra = BDDInfra.from_config(bdd_config)
    yield infra
    infra.stop()


# ── AWS client shortcuts ───────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def sqs_client(bdd_infra):
    return bdd_infra.sqs


@pytest.fixture(scope="session")
def sns_client(bdd_infra):
    return bdd_infra.sns


@pytest.fixture(scope="session")
def s3_client(bdd_infra):
    return bdd_infra.s3


@pytest.fixture(scope="session")
def sqs_queue_url(bdd_infra):
    urls = bdd_infra.queue_urls
    assert urls, "No SQS queues configured in BDDConfig.sqs_queues"
    return next(iter(urls.values()))


@pytest.fixture(scope="session")
def sns_capture_url(bdd_infra):
    """URL of the first SNS capture queue (subscribed to the first SNS topic).

    For modules with multiple topics use ``bdd_infra.sns_capture_urls["topic-name"]``
    directly in a module-specific fixture.
    """
    urls = bdd_infra.sns_capture_urls
    assert urls, "No SNS topics configured in BDDConfig.sns_topics"
    return next(iter(urls.values()))


# ── Per-test reset (autouse) ───────────────────────────────────────────────────


@pytest.fixture
def db_tables() -> list[str]:
    """Override in a module conftest to list the tables to truncate before each test."""
    return []


@pytest.fixture(autouse=True)
def reset_between_tests(bdd_infra, db_tables):
    if db_tables:
        bdd_infra.truncate_tables(*db_tables)
    bdd_infra.drain_all_queues()
    yield
    bdd_infra.drain_all_queues()


# ── DB seeding ────────────────────────────────────────────────────────────────


@pytest.fixture
def db_seed(bdd_infra):
    """Open SQLAlchemy session for inserting seed data in a step or fixture.

    The session is committed and closed automatically when the fixture tears
    down (after the test). Call ``session.commit()`` or ``session.flush()``
    inside the step if subsequent steps need the data visible before teardown.

        @given("a category exists")
        def seed_category(db_seed):
            db_seed.add(Category(name="Electronics"))
            db_seed.commit()          # flush to DB so HTTP routes can read it
    """
    with bdd_infra.seed_session() as session:
        yield session


# ── Step state ─────────────────────────────────────────────────────────────────


@pytest.fixture
def scenario_context() -> dict:
    """Fresh dict per test scenario for accumulating state across BDD steps.

    Use this instead of defining a module-specific ``<name>_context`` fixture.
    Step functions declare it as a parameter:

        @when('I create a thing with name "{name}"')
        def create_thing(bdd_client, scenario_context, name):
            scenario_context["response"] = bdd_client.json_post("/things", {"name": name})
    """
    return {}


# ── HTTP client ────────────────────────────────────────────────────────────────


@pytest.fixture
def bdd_client(flask_app) -> Generator[BDDClient, None, None]:
    with flask_app.test_client() as raw:
        yield BDDClient(raw)

from typing import List

import pytest

from lib.client import BDDClient
from lib.infra import BDDInfra


@pytest.fixture(scope="session")
def bdd_infra(bdd_config) -> BDDInfra:
    infra = BDDInfra.from_config(bdd_config)
    yield infra
    infra.stop()


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


@pytest.fixture
def db_tables() -> List[str]:
    return []


@pytest.fixture(autouse=True)
def reset_between_tests(bdd_infra, db_tables):
    tables = db_tables
    if tables:
        bdd_infra.truncate_tables(*tables)
    bdd_infra.drain_all_queues()
    yield
    bdd_infra.drain_all_queues()


@pytest.fixture
def bdd_client(flask_app) -> BDDClient:
    with flask_app.test_client() as raw:
        yield BDDClient(raw)

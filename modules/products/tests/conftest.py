import sys
import os

_tests_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.abspath(os.path.join(_tests_dir, "..", "src"))
_modules_dir = os.path.abspath(os.path.join(_tests_dir, "..", ".."))

for _p in (_src_dir, _modules_dir, _tests_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
from lib.config import BDDConfig
from lib.infra import BDDInfra
from lib.client import BDDClient

from product_steps import *  # noqa: F401,F403

from products.app import create_app
from products.db import Base
from products.service import ProductService
import products.blueprint as bp_module

_QUEUE  = "products-events"
_TOPIC  = "products-alerts"
_BUCKET = "products-assets"


@pytest.fixture(scope="session")
def _p_config():
    return BDDConfig.from_env(
        db_base=Base,
        sqs_queues=[_QUEUE],
        sns_topics=[_TOPIC],
        s3_buckets=[_BUCKET],
    )


@pytest.fixture(scope="session")
def _p_infra(_p_config):
    infra = BDDInfra.from_config(_p_config)
    yield infra
    infra.stop()


@pytest.fixture
def products_sqs_client(_p_infra):
    return _p_infra.sqs


@pytest.fixture
def products_queue_url(_p_infra):
    return _p_infra.queue_urls[_QUEUE]


@pytest.fixture(autouse=True)
def _p_reset(_p_infra):
    _p_infra.truncate_tables("products")
    _p_infra.drain_all_queues()
    yield
    _p_infra.drain_all_queues()


@pytest.fixture
def _p_flask(_p_infra):
    app = create_app(db_url=_p_infra.db_url)
    app.config["TESTING"] = True
    _sessions = []

    def _patched():
        s = _p_infra.make_session()
        _sessions.append(s)
        return ProductService(
            session=s,
            sqs_client=_p_infra.sqs,
            sns_client=_p_infra.sns,
            s3_client=_p_infra.s3,
            sqs_queue_url=_p_infra.queue_urls[_QUEUE],
            sns_topic_arn=_p_infra.topic_arns[_TOPIC],
            s3_bucket=_BUCKET,
        )

    @app.teardown_request
    def _cleanup(_=None):
        for s in _sessions:
            s.close()
        _sessions.clear()

    bp_module._make_service = _patched
    return app


@pytest.fixture
def products_bdd_client(_p_flask):
    with _p_flask.test_client() as raw:
        yield BDDClient(raw)

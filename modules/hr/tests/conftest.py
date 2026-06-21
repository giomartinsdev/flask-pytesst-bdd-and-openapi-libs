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

from hr_steps import *  # noqa: F401,F403

from hr.app import create_app
from hr.db import Base
from hr.service import HRService
import hr.blueprint as bp_module

_HR_QUEUE = "hr-events"
_HR_TOPIC = "hr-alerts"


@pytest.fixture(scope="session")
def _hr_config():
    return BDDConfig.from_env(
        db_base=Base,
        db_type="sqlserver",
        sqs_queues=[_HR_QUEUE],
        sns_topics=[_HR_TOPIC],
    )


@pytest.fixture(scope="session")
def _hr_infra(_hr_config):
    infra = BDDInfra.from_config(_hr_config)
    yield infra
    infra.stop()


@pytest.fixture
def hr_sqs_client(_hr_infra):
    return _hr_infra.sqs


@pytest.fixture
def hr_queue_url(_hr_infra):
    return _hr_infra.queue_urls[_HR_QUEUE]


@pytest.fixture(autouse=True)
def _hr_reset(_hr_infra):
    _hr_infra.truncate_tables("employees")
    _hr_infra.drain_all_queues()
    yield
    _hr_infra.drain_all_queues()


@pytest.fixture
def _hr_flask(_hr_infra):
    app = create_app(db_url=_hr_infra.db_url)
    app.config["TESTING"] = True
    _sessions = []

    def _patched():
        s = _hr_infra.make_session()
        _sessions.append(s)
        return HRService(
            session=s,
            sqs_client=_hr_infra.sqs,
            sns_client=_hr_infra.sns,
            sqs_queue_url=_hr_infra.queue_urls[_HR_QUEUE],
            sns_topic_arn=_hr_infra.topic_arns[_HR_TOPIC],
        )

    @app.teardown_request
    def _cleanup(_=None):
        for s in _sessions:
            s.close()
        _sessions.clear()

    bp_module._make_service = _patched
    return app


@pytest.fixture
def hr_bdd_client(_hr_flask):
    with _hr_flask.test_client() as raw:
        yield BDDClient(raw)

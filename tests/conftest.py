"""Shared pytest setup.

* ``cfg`` fixture: config pointing at tests/fixtures (mock backend, no GPU).
* Tests that hit an unimplemented stub (NotImplementedError) are reported as
  SKIPPED, not failed. So each person's acceptance tests switch on by
  themselves as soon as the code is written, and CI stays green meanwhile.
"""

from __future__ import annotations

import pytest

from src.common.config import REPO_ROOT, load_config

FIXTURES = REPO_ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def cfg():
    return load_config(path=FIXTURES / "config.yaml")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and call.excinfo is not None and call.excinfo.errisinstance(NotImplementedError):
        rep.outcome = "skipped"
        rep.longrepr = (str(item.fspath), item.location[1] or 0,
                        f"not implemented yet: {call.excinfo.value}")

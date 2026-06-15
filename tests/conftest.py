# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import pytest


@pytest.fixture(autouse=True)
def _clear_version_cache():
    """Reset the process-global OpenSearch version cache before every test.

    ``get_opensearch_version`` now reads through ``opensearch.version_cache``, which
    is module-global state that persists across tests. Tests that mock a cluster
    version (directly or via a tool call hitting the version gate) would otherwise
    see a value cached by an earlier test under the shared single-mode key. Clearing
    before each test restores isolation without any production change.
    """
    from opensearch.version_cache import clear_cache

    clear_cache()
    yield


@pytest.fixture(autouse=True)
def _reset_global_mode():
    """Reset the process-global server mode after every test.

    ``global_state`` holds the server mode as module-global state; several tests call
    ``set_mode('multi')`` and do not reset it, which can leak into later tests that
    assume the default ``'single'`` (e.g. the version-cache header-auth bypass, which
    branches on ``get_mode()``). Restoring the prior value after each test keeps that
    global isolated without changing production behavior.
    """
    from mcp_server_opensearch import global_state

    saved = global_state._current_mode
    yield
    global_state._current_mode = saved


def pytest_addoption(parser):
    parser.addoption(
        '--run-evals',
        action='store_true',
        default=False,
        help='Run LLM eval tests that call the Anthropic API (requires ANTHROPIC_API_KEY)',
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption('--run-evals'):
        skip = pytest.mark.skip(
            reason='LLM eval tests are skipped by default; pass --run-evals to run them'
        )
        for item in items:
            if item.get_closest_marker('eval'):
                item.add_marker(skip)
    elif not os.environ.get('ANTHROPIC_API_KEY'):
        skip = pytest.mark.skip(reason='ANTHROPIC_API_KEY environment variable is not set')
        for item in items:
            if item.get_closest_marker('eval'):
                item.add_marker(skip)

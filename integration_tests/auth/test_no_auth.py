# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
from integration_tests.framework.assertions import (
    _has_error_flag,
    assert_tool_error,
    assert_tool_success,
)
from integration_tests.framework.client import mcp_client
from integration_tests.framework.server import MCPServerProcess


@pytest.mark.auth
@pytest.mark.no_auth
class TestNoAuth:
    """Verify anonymous / no-auth mode behavior."""

    async def test_no_auth_cluster(self, seed_test_index):
        """If the cluster allows anonymous access, no-auth should work.

        If the cluster requires auth, the tool call should return an error.
        Either way, the server should start and respond.
        """
        url = os.environ.get('IT_OPENSEARCH_URL')
        if not url:
            pytest.skip('IT_OPENSEARCH_URL not set')

        server = MCPServerProcess(
            env={
                'OPENSEARCH_URL': url,
                'OPENSEARCH_NO_AUTH': 'true',
            },
        )
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                result = await session.call_tool('ClusterHealthTool', arguments={})
                # Accept either success or error — we just verify the server handles it
                if _has_error_flag(result):
                    assert_tool_error(result)
                else:
                    assert_tool_success(result)
        finally:
            await server.stop()

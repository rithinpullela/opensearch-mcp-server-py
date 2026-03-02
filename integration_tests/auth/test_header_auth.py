# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.aws_helpers import build_header_auth_headers
from integration_tests.framework.client import mcp_client
from integration_tests.framework.constants import TEST_INDEX
from integration_tests.framework.server import MCPServerProcess


@pytest.mark.auth
@pytest.mark.header_auth
class TestHeaderAuth:
    """Verify that header-based auth works (creds sent per-request in headers)."""

    async def test_list_index(self, header_auth_client):
        result = await header_auth_client.call_tool('ListIndexTool', arguments={})
        response = assert_tool_success(result)
        assert TEST_INDEX in response

    async def test_search_index(self, header_auth_client):
        result = await header_auth_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match_all": {}}}',
            },
        )
        response = assert_tool_success(result)
        assert 'Test document' in response

    async def test_generic_api(self, header_auth_client):
        result = await header_auth_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={'path': '/_cluster/health', 'method': 'GET'},
        )
        assert_tool_success(result)


@pytest.mark.auth
@pytest.mark.header_auth
class TestHeaderAuthPriority:
    """Verify header auth takes precedence over server-side credentials."""

    async def test_header_auth_overrides_basic_auth(self, seed_test_index):
        """Start server with BOTH basic auth env AND header auth flag.

        Send headers with AWS creds — verify the header creds are used
        (not the basic auth creds configured on the server).
        """
        env_vars = {
            'IT_OPENSEARCH_URL': '',
            'IT_BASIC_AUTH_USERNAME': '',
            'IT_BASIC_AUTH_PASSWORD': '',
        }
        for key in env_vars:
            val = os.environ.get(key)
            if not val:
                pytest.skip(f'{key} not set')
            env_vars[key] = val

        server = MCPServerProcess(
            env={
                'OPENSEARCH_URL': env_vars['IT_OPENSEARCH_URL'],
                'OPENSEARCH_USERNAME': env_vars['IT_BASIC_AUTH_USERNAME'],
                'OPENSEARCH_PASSWORD': env_vars['IT_BASIC_AUTH_PASSWORD'],
                'OPENSEARCH_HEADER_AUTH': 'true',
            },
        )
        await server.start()
        try:
            headers = build_header_auth_headers()
            async with mcp_client(server.url, headers=headers) as session:
                result = await session.call_tool('ListIndexTool', arguments={})
                response = assert_tool_success(result)
                assert seed_test_index in response
        finally:
            await server.stop()

# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.auth
@pytest.mark.basic_auth
class TestBasicAuth:
    """Verify that basic auth (username/password) connects and tools work."""

    async def test_list_tools(self, basic_auth_client):
        tools = await basic_auth_client.list_tools()
        tool_names = {t.name for t in tools.tools}
        assert 'ListIndexTool' in tool_names

    async def test_list_index(self, basic_auth_client):
        result = await basic_auth_client.call_tool('ListIndexTool', arguments={})
        response = assert_tool_success(result)
        assert TEST_INDEX in response

    async def test_search_index(self, basic_auth_client):
        result = await basic_auth_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match_all": {}}}',
            },
        )
        response = assert_tool_success(result)
        assert 'Test document' in response

# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_error, assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestSearchIndexTool:
    # -- Happy paths --

    async def test_match_all(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={'index': TEST_INDEX, 'query_dsl': '{"query": {"match_all": {}}}'},
        )
        response = assert_tool_success(result)
        assert 'Test document' in response

    async def test_specific_field_query(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match": {"category": "A"}}}',
            },
        )
        response = assert_tool_success(result)
        assert 'Test document 1' in response

    async def test_csv_output_format(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match_all": {}}}',
                'format': 'csv',
            },
        )
        assert_tool_success(result)

    async def test_size_parameter(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match_all": {}}}',
                'size': 1,
            },
        )
        assert_tool_success(result)

    async def test_empty_results_is_not_error(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match": {"title": "xyznonexistent"}}}',
            },
        )
        assert_tool_success(result)

    # -- Bad paths --

    async def test_nonexistent_index_returns_error(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': 'nonexistent_xyz_404_test',
                'query_dsl': '{"query": {"match_all": {}}}',
            },
        )
        assert_tool_error(result)

    async def test_malformed_query_dsl_returns_error(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"bad_field": {"unknown_query": true}}',
            },
        )
        assert_tool_error(result)

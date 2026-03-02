# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import _has_error_flag, assert_tool_error, assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestListIndexTool:
    async def test_list_all_indices(self, default_client):
        result = await default_client.call_tool('ListIndexTool', arguments={})
        response = assert_tool_success(result)
        assert TEST_INDEX in response

    async def test_list_specific_index(self, default_client):
        result = await default_client.call_tool('ListIndexTool', arguments={'index': TEST_INDEX})
        response = assert_tool_success(result)
        assert TEST_INDEX in response

    async def test_list_names_only(self, default_client):
        result = await default_client.call_tool(
            'ListIndexTool', arguments={'include_detail': False}
        )
        response = assert_tool_success(result)
        assert TEST_INDEX in response

    async def test_nonexistent_index_pattern(self, default_client):
        result = await default_client.call_tool(
            'ListIndexTool', arguments={'index': 'nonexistent_xyz_404_test'}
        )
        # ListIndexTool may return error or empty results for non-existent index
        if _has_error_flag(result):
            assert_tool_error(result)
        else:
            assert_tool_success(result)

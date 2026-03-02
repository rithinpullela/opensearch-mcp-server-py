# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success


@pytest.mark.tools
class TestClusterHealthTool:
    async def test_happy_path(self, default_client):
        result = await default_client.call_tool('ClusterHealthTool', arguments={})
        response = assert_tool_success(result)
        assert any(s in response for s in ['green', 'yellow', 'red'])

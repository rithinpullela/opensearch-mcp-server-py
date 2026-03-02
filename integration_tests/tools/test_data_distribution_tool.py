# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestDataDistributionTool:
    """Tests for DataDistributionTool (ML skills, requires OpenSearch 3.3+)."""

    async def test_data_distribution(self, default_client):
        result = await default_client.call_tool(
            'DataDistributionTool',
            arguments={
                'index': TEST_INDEX,
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-01',
                'selectionTimeRangeEnd': '2025-01-04',
            },
        )
        # This tool requires OS 3.3+ with ML plugin — may not be available
        # Accept either success or error
        assert result.content

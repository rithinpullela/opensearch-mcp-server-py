# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestLogPatternAnalysisTool:
    """Tests for LogPatternAnalysisTool (ML skills, requires OpenSearch 3.3+)."""

    async def test_log_pattern_analysis(self, default_client):
        result = await default_client.call_tool(
            'LogPatternAnalysisTool',
            arguments={
                'index': TEST_INDEX,
                'logFieldName': 'title',
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-01',
                'selectionTimeRangeEnd': '2025-01-04',
            },
        )
        # This tool requires OS 3.3+ with ML plugin — may not be available
        assert result.content

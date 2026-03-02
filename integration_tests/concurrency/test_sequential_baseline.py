# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest


@pytest.mark.concurrency
class TestSequentialBaseline:
    async def test_sequential_calls_succeed(self, sequential_baseline):
        """Verify the baseline runs and returns a positive total time."""
        assert sequential_baseline > 0

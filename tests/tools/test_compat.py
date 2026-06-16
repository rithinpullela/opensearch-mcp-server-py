# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the extracted version-compatibility gate (tools.compat)."""

import pytest
from tools.compat import build_version_unsupported_message, check_tool_compatibility


def _registry(min_version=None, max_version=None, display_name='MyTool'):
    spec = {'display_name': display_name}
    if min_version is not None:
        spec['min_version'] = min_version
    if max_version is not None:
        spec['max_version'] = max_version
    return {'MyTool': spec}


def _fetcher(version):
    async def fetch(_args):
        return version

    return fetch


class TestBuildMessage:
    def test_min_and_max(self):
        msg = build_version_unsupported_message('MyTool', '1.0.0', '2.0.0', '3.0.0')
        assert (
            msg == "Tool 'MyTool' is not supported for this OpenSearch version "
            '(current version: 1.0.0). Supported version: 2.0.0 to 3.0.0.'
        )

    def test_min_only(self):
        msg = build_version_unsupported_message('MyTool', '1.0.0', '2.0.0', '')
        assert msg.endswith('Supported version: 2.0.0 or later.')

    def test_max_only(self):
        msg = build_version_unsupported_message('MyTool', '5.0.0', '', '3.0.0')
        assert msg.endswith('Supported version: up to 3.0.0.')

    def test_no_bounds_omits_supported_clause(self):
        msg = build_version_unsupported_message('MyTool', '1.0.0', '', '')
        assert 'Supported version' not in msg
        assert msg.endswith('(current version: 1.0.0).')


class TestCheckToolCompatibility:
    async def test_compatible_does_not_raise(self):
        # cluster 2.5.0 satisfies min 2.0.0
        await check_tool_compatibility('MyTool', _registry(min_version='2.0.0'), _fetcher('2.5.0'))

    async def test_incompatible_raises_exact_message(self):
        with pytest.raises(Exception) as exc:
            await check_tool_compatibility(
                'MyTool', _registry(min_version='3.0.0'), _fetcher('2.0.0')
            )
        assert str(exc.value) == (
            "Tool 'MyTool' is not supported for this OpenSearch version "
            '(current version: 2.0.0). Supported version: 3.0.0 or later.'
        )

    async def test_none_version_is_compatible(self):
        # fail-open: a None version (fetch error / serverless) passes the gate
        await check_tool_compatibility('MyTool', _registry(min_version='3.0.0'), _fetcher(None))

    async def test_no_version_bounds_always_compatible(self):
        await check_tool_compatibility('MyTool', _registry(), _fetcher('1.0.0'))

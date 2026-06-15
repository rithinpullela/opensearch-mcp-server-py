# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the immutable ServerContext."""

import dataclasses
import pytest
from mcp_server_opensearch.context import ServerContext


class TestServerContext:
    def test_defaults_match_global_state_defaults(self):
        # Mirrors global_state: mode defaults to 'single', profile/config empty.
        ctx = ServerContext()
        assert ctx.mode == 'single'
        assert ctx.profile == ''
        assert ctx.config_file_path == ''
        assert ctx.is_multi is False
        assert ctx.has_config_file is False

    def test_multi_mode_flags(self):
        ctx = ServerContext(mode='multi', config_file_path='/etc/clusters.yml')
        assert ctx.is_multi is True
        assert ctx.has_config_file is True

    def test_is_frozen(self):
        ctx = ServerContext()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.mode = 'multi'  # type: ignore[misc]

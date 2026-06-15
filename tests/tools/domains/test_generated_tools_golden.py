# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Golden-snapshot lock for the 4 static (ex-generated) tools.

Asserts that the hand-written static tools reproduce, field-for-field, what the
runtime OpenAPI generator produced — captured in
``tests/fixtures/generated_tools_golden.json`` before the generator was removed.

Fidelity rules (per AUDIT_FINDINGS.md §3.3 and DESIGN_DECISIONS.md):
- ``input_schema`` must be **dict-equal** to the snapshot (the snapshot was stored
  with sorted keys for readable diffs; dict equality is order-independent and is the
  correct semantic oracle).
- ``display_name``, ``description``, and ``http_methods`` strings must be byte-exact.
- ``min_version``/``max_version`` must be the raw spec strings (``'1.0'``,
  ``'99.99.99'``) — not normalized to ``'1.0.0'``.
"""

import json
import pytest
from pathlib import Path
from tools.domains.generated.register import build_generated_tools


FIXTURE = (
    Path(__file__).resolve().parents[3] / 'tests' / 'fixtures' / 'generated_tools_golden.json'
)


@pytest.fixture(scope='module')
def golden():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope='module')
def built():
    # Inject a no-op version_check so we don't import the live registry/client.
    async def _noop(_name, _args):
        return None

    return build_generated_tools(version_check=_noop)


TOOL_NAMES = ['MsearchTool', 'ExplainTool', 'CountTool', 'ClusterHealthTool']


class TestGeneratedToolsGolden:
    def test_all_four_tools_present(self, built):
        assert set(built.keys()) == set(TOOL_NAMES)

    def test_order_matches_generator(self, built):
        # Generator emitted them in this order; preserve it.
        assert list(built.keys()) == TOOL_NAMES

    @pytest.mark.parametrize('name', TOOL_NAMES)
    def test_input_schema_dict_equal(self, name, built, golden):
        assert built[name]['input_schema'] == golden[name]['input_schema']

    @pytest.mark.parametrize('name', TOOL_NAMES)
    def test_display_name_exact(self, name, built, golden):
        assert built[name]['display_name'] == golden[name]['display_name']

    @pytest.mark.parametrize('name', TOOL_NAMES)
    def test_description_exact(self, name, built, golden):
        assert built[name]['description'] == golden[name]['description']

    @pytest.mark.parametrize('name', TOOL_NAMES)
    def test_http_methods_exact(self, name, built, golden):
        assert built[name]['http_methods'] == golden[name]['http_methods']

    @pytest.mark.parametrize('name', TOOL_NAMES)
    def test_versions_raw_strings(self, name, built, golden):
        assert built[name]['min_version'] == golden[name]['min_version'] == '1.0'
        assert built[name]['max_version'] == golden[name]['max_version'] == '99.99.99'

    @pytest.mark.parametrize('name', TOOL_NAMES)
    def test_required_keys_present(self, name, built):
        spec = built[name]
        for key in ('display_name', 'description', 'input_schema', 'function', 'args_model'):
            assert key in spec

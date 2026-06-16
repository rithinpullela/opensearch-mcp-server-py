# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Direct tests for ToolRegistry / ToolSpec / DuplicateToolError.

The registry's one production value-add is fail-loud validation at compose time
(duplicate keys + required-key checks); these tests exercise it directly so the
guarantee is not "dead on arrival" (it fires once at import via compose_registry,
where the live sub-registries happen to be collision-free).
"""

import pytest
from tools.registry import DuplicateToolError, ToolRegistry


def _spec(name='X'):
    return {
        'display_name': name,
        'description': 'd',
        'input_schema': {'type': 'object', 'properties': {}},
        'function': lambda args: [],
        'args_model': dict,
        'http_methods': 'GET',
    }


class TestToolRegistry:
    def test_add_then_read_back(self):
        r = ToolRegistry()
        r.add('A', _spec('A'))
        assert 'A' in r
        assert r['A']['display_name'] == 'A'
        assert r.get('A') is r['A']
        assert r.get('missing') is None
        assert len(r) == 1
        assert list(r.keys()) == ['A']

    def test_insertion_order_preserved(self):
        r = ToolRegistry()
        for n in ('C', 'A', 'B'):
            r.add(n, _spec(n))
        assert list(r.keys()) == ['C', 'A', 'B']
        assert list(r) == ['C', 'A', 'B']  # __iter__ yields keys in order

    def test_duplicate_key_raises(self):
        r = ToolRegistry()
        r.add('A', _spec('A'))
        with pytest.raises(DuplicateToolError, match='already registered'):
            r.add('A', _spec('A'))

    def test_update_detects_duplicate_across_groups(self):
        r = ToolRegistry()
        r.update({'A': _spec('A'), 'B': _spec('B')})
        with pytest.raises(DuplicateToolError):
            r.update({'B': _spec('B')})  # B collides

    @pytest.mark.parametrize(
        'missing',
        ['display_name', 'description', 'input_schema', 'function', 'args_model', 'http_methods'],
    )
    def test_missing_required_key_raises(self, missing):
        spec = _spec('A')
        del spec[missing]
        r = ToolRegistry()
        with pytest.raises(ValueError, match='missing required key'):
            r.add('A', spec)

    def test_http_methods_is_required(self):
        # Regression: http_methods must be required because the write-protection
        # filter substring-matches 'GET' against it.
        spec = _spec('A')
        del spec['http_methods']
        r = ToolRegistry()
        with pytest.raises(ValueError, match='http_methods'):
            r.add('A', spec)

    def test_as_dict_is_a_plain_dict_copy(self):
        r = ToolRegistry()
        r.add('A', _spec('A'))
        d = r.as_dict()
        assert type(d) is dict
        d['B'] = _spec('B')  # mutating the copy must not affect the registry
        assert 'B' not in r
        # values are the same spec objects (shallow copy)
        assert d['A'] is r['A']

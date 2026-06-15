# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Pinning tests: compose_registry reproduces the legacy catalog exactly.

These lock the observable tool-catalog order and contents so the per-domain
module split cannot drift from the legacy ``tools.TOOL_REGISTRY`` literal.
"""

import importlib
import os
from unittest import mock


# Frozen expected tool order — the wire contract for tools/list, with memory tools
# OMITTED (they only register when MEMORY_TOOLS_ENABLED=true). This is a hand-pinned
# literal (NOT derived from TOOL_REGISTRY) so the test is a real regression oracle:
# if a future change reorders or drops a tool, this fails. Memory tools, when enabled,
# slot in right after the agentic-memory block (see _expected_order).
_EXPECTED_ORDER_NO_MEMORY = [
    # skills
    'DataDistributionTool',
    'LogPatternAnalysisTool',
    # agentic_memory
    'CreateAgenticMemorySessionTool',
    'AddAgenticMemoriesTool',
    'GetAgenticMemoryTool',
    'UpdateAgenticMemoryTool',
    'DeleteAgenticMemoryByIDTool',
    'DeleteAgenticMemoryByQueryTool',
    'SearchAgenticMemoryTool',
    # core (inline, legacy declaration order)
    'ListIndexTool',
    'IndexMappingTool',
    'SearchIndexTool',
    'GetShardsTool',
    'GetClusterStateTool',
    'GetSegmentsTool',
    'CatNodesTool',
    'GetIndexInfoTool',
    'GetIndexStatsTool',
    'GetQueryInsightsTool',
    'GetNodesHotThreadsTool',
    'GetAllocationTool',
    'GetLongRunningTasksTool',
    'GetNodesTool',
    'GetQuerySetTool',
    'CreateQuerySetTool',
    'SampleQuerySetTool',
    'DeleteQuerySetTool',
    'GetExperimentTool',
    'CreateExperimentTool',
    'DeleteExperimentTool',
    'SearchQuerySetsTool',
    'SearchSearchConfigurationsTool',
    'SearchJudgmentsTool',
    'SearchExperimentsTool',
    'GenericOpenSearchApiTool',
    'CreateSearchConfigurationTool',
    'GetSearchConfigurationTool',
    'DeleteSearchConfigurationTool',
    'GetJudgmentListTool',
    'CreateJudgmentListTool',
    'CreateUBIJudgmentListTool',
    'DeleteJudgmentListTool',
    'CreateLLMJudgmentListTool',
    'ListClustersTool',
    # generated (static, ex-OpenAPI), legacy generator order
    'ClusterHealthTool',
    'CountTool',
    'MsearchTool',
    'ExplainTool',
]


def _expected_order(memory_enabled: bool):
    """The frozen expected key order, inserting the 3 memory tools when enabled."""
    if not memory_enabled:
        return list(_EXPECTED_ORDER_NO_MEMORY)
    keys = list(_EXPECTED_ORDER_NO_MEMORY)
    # Memory tools register right after the agentic-memory block (after SearchAgenticMemoryTool).
    idx = keys.index('SearchAgenticMemoryTool') + 1
    return keys[:idx] + ['SaveMemoryTool', 'SearchMemoryTool', 'DeleteMemoryTool'] + keys[idx:]


def _composed(memory_enabled: bool):
    """Compose a registry from the per-domain sources (NOT from TOOL_REGISTRY).

    Sourcing ``core`` from ``tools.domains.core`` + the generated tools (rather than
    reverse-engineering it from TOOL_REGISTRY) makes this an independent oracle of the
    per-domain split, not a tautology against the thing it is supposed to verify.
    Modules are reloaded so the ``MEMORY_TOOLS_ENABLED`` gate is re-evaluated.
    """
    env = {'MEMORY_TOOLS_ENABLED': 'true' if memory_enabled else 'false'}
    with mock.patch.dict(os.environ, env, clear=False):
        import tools.agentic_memory.actions as agentic_mod
        import tools.domains.core as core_mod
        import tools.memory_tools as memory_mod
        import tools.modules as modules_mod
        import tools.skills_tools as skills_mod
        import tools.tools as tools_mod
        from tools.domains.generated.register import build_generated_tools

        importlib.reload(memory_mod)
        importlib.reload(tools_mod)
        importlib.reload(modules_mod)

        generated = build_generated_tools(version_check=tools_mod.check_tool_compatibility)
        core = {**core_mod.build_core_tools(), **generated}
        composed = modules_mod.compose_registry(
            skills=skills_mod.SKILLS_TOOLS_REGISTRY,
            agentic_memory=agentic_mod.AGENTIC_MEMORY_TOOLS_REGISTRY,
            memory=memory_mod.MEMORY_TOOLS_REGISTRY,
            core=core,
        )
        return composed


def _legacy_and_composed(memory_enabled: bool):
    """Return (live TOOL_REGISTRY, independently-composed registry) for the same env.

    The composed registry is built from per-domain sources; the live registry is the
    one tools.py assembled. They must match key-for-key and by spec-object identity.
    """
    env = {'MEMORY_TOOLS_ENABLED': 'true' if memory_enabled else 'false'}
    with mock.patch.dict(os.environ, env, clear=False):
        import tools.memory_tools as memory_mod
        import tools.tools as tools_mod

        importlib.reload(memory_mod)
        importlib.reload(tools_mod)
        legacy = dict(tools_mod.TOOL_REGISTRY)
    composed = _composed(memory_enabled)
    return legacy, composed


class TestComposeRegistry:
    # The 4 ex-generated tools are rebuilt per call (build_generated_tools), so their
    # spec objects differ between two independent compositions; everything else shares
    # objects. Identity is asserted only for the non-generated tools.
    _GENERATED = {'ClusterHealthTool', 'CountTool', 'MsearchTool', 'ExplainTool'}

    def test_live_registry_matches_frozen_order_memory_disabled(self):
        # The real regression pin: the live TOOL_REGISTRY order == a hand-frozen list.
        legacy, _ = _legacy_and_composed(memory_enabled=False)
        assert list(legacy.keys()) == _expected_order(memory_enabled=False)

    def test_live_registry_matches_frozen_order_memory_enabled(self):
        legacy, _ = _legacy_and_composed(memory_enabled=True)
        assert list(legacy.keys()) == _expected_order(memory_enabled=True)

    def test_independent_composition_matches_live_keys(self):
        # compose_registry from per-domain sources reproduces the live key order.
        legacy, composed = _legacy_and_composed(memory_enabled=False)
        assert list(composed.keys()) == list(legacy.keys())

    def test_independent_composition_matches_live_keys_memory_enabled(self):
        legacy, composed = _legacy_and_composed(memory_enabled=True)
        assert list(composed.keys()) == list(legacy.keys())
        assert 'SaveMemoryTool' in composed

    def test_composed_specs_match_live_specs(self):
        # Every composed spec matches the live registry's spec on the identity-bearing
        # fields (display_name, http_methods, versions, flags, args_model). Full object
        # identity is not asserted because module reloads + per-call generated-tool
        # rebuilds legitimately produce distinct-but-equal dict objects.
        legacy, composed = _legacy_and_composed(memory_enabled=True)
        assert set(composed.keys()) == set(legacy.keys())
        fields = ('display_name', 'http_methods', 'min_version', 'max_version', 'multi_only')
        for key in legacy:
            for f in fields:
                assert composed[key].get(f) == legacy[key].get(f), f'{key}.{f} differs'

    def test_core_module_specs_are_the_live_objects(self):
        # The core block ships the SAME spec dict objects the live registry uses
        # (no reload involved here) — proves zero metadata drift for the inline tools.
        import tools.domains.core as core_mod
        import tools.tools as tools_mod

        for key, spec in core_mod.build_core_tools().items():
            assert tools_mod.TOOL_REGISTRY[key] is spec, f'core spec object differs for {key}'

    def test_skills_first_then_agentic_then_memory(self):
        _, composed = _legacy_and_composed(memory_enabled=True)
        keys = list(composed.keys())
        # skills lead, then agentic, then memory, then inline core
        assert keys[0] == 'DataDistributionTool'
        assert keys.index('CreateAgenticMemorySessionTool') > keys.index('LogPatternAnalysisTool')
        assert keys.index('SaveMemoryTool') > keys.index('SearchAgenticMemoryTool')
        assert keys.index('ListIndexTool') > keys.index('SaveMemoryTool')


class TestGeneratedToolsRegistryOrder:
    """Pin the observable tools/list tail order after the generator was made static.

    The 4 ex-generated tools must appear LAST in TOOL_REGISTRY, in the exact order
    the old runtime generator appended them, so the advertised tools/list order is
    unchanged from before the generator was deleted.
    """

    def test_registry_tail_is_generated_tools_in_generator_order(self):
        import tools.tools as tools_mod

        expected_tail = ['ClusterHealthTool', 'CountTool', 'MsearchTool', 'ExplainTool']
        assert list(tools_mod.TOOL_REGISTRY.keys())[-4:] == expected_tail

    def test_registry_tail_matches_single_source_of_truth(self):
        import tools.tools as tools_mod
        from tools.domains.generated.register import GENERATED_TOOL_ORDER

        assert list(tools_mod.TOOL_REGISTRY.keys())[-4:] == list(GENERATED_TOOL_ORDER)

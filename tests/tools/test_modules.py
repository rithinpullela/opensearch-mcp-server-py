# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Pinning tests: compose_registry reproduces the legacy catalog exactly.

These lock the observable tool-catalog order and contents so the per-domain
module split cannot drift from the legacy ``tools.TOOL_REGISTRY`` literal.
"""

import importlib
import os
from unittest import mock


def _legacy_and_composed(memory_enabled: bool):
    """Build the legacy registry and the composed registry under the same env.

    Returns (legacy_dict, composed_registry). Modules are reloaded so the
    ``MEMORY_TOOLS_ENABLED``-gated memory sub-registry reflects ``memory_enabled``.
    """
    env = {'MEMORY_TOOLS_ENABLED': 'true' if memory_enabled else 'false'}
    with mock.patch.dict(os.environ, env, clear=False):
        import tools.skills_tools as skills_mod
        import tools.memory_tools as memory_mod
        import tools.agentic_memory.actions as agentic_mod
        import tools.tools as tools_mod
        import tools.modules as modules_mod

        # Reload so the env-gated memory registry is recomputed for this case.
        importlib.reload(memory_mod)
        importlib.reload(tools_mod)
        importlib.reload(modules_mod)

        legacy = dict(tools_mod.TOOL_REGISTRY)

        skills = skills_mod.SKILLS_TOOLS_REGISTRY
        agentic = agentic_mod.AGENTIC_MEMORY_TOOLS_REGISTRY
        memory = memory_mod.MEMORY_TOOLS_REGISTRY
        sub_keys = set(skills) | set(agentic) | set(memory)
        # The legacy inline block = everything in TOOL_REGISTRY not in a sub-registry,
        # in its existing order.
        core = {k: v for k, v in tools_mod.TOOL_REGISTRY.items() if k not in sub_keys}

        composed = modules_mod.compose_registry(
            skills=skills, agentic_memory=agentic, memory=memory, core=core
        )
        return legacy, composed


class TestComposeRegistry:
    def test_order_and_keys_match_legacy_memory_disabled(self):
        legacy, composed = _legacy_and_composed(memory_enabled=False)
        assert list(composed.keys()) == list(legacy.keys())

    def test_order_and_keys_match_legacy_memory_enabled(self):
        legacy, composed = _legacy_and_composed(memory_enabled=True)
        assert list(composed.keys()) == list(legacy.keys())
        # memory tools present when enabled
        assert 'SaveMemoryTool' in composed

    def test_values_identical(self):
        legacy, composed = _legacy_and_composed(memory_enabled=True)
        for key in legacy:
            assert composed[key] is legacy[key], f'spec object differs for {key}'

    def test_skills_first_then_agentic_then_memory(self):
        _, composed = _legacy_and_composed(memory_enabled=True)
        keys = list(composed.keys())
        # skills lead, then agentic, then memory, then inline core
        assert keys[0] == 'DataDistributionTool'
        assert keys.index('CreateAgenticMemorySessionTool') > keys.index('LogPatternAnalysisTool')
        assert keys.index('SaveMemoryTool') > keys.index('SearchAgenticMemoryTool')
        assert keys.index('ListIndexTool') > keys.index('SaveMemoryTool')

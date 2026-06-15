# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tool catalog composition manifest.

Defines the canonical *order* in which tool groups are assembled into the
registry and a :func:`compose_registry` helper that builds an ordered
:class:`~tools.registry.ToolRegistry` from the existing per-group sub-registries.

Why
---
The legacy catalog is one ``dict`` literal in ``tools.py`` built by spreading the
sub-registries in a fixed order::

    TOOL_REGISTRY = {
        **SKILLS_TOOLS_REGISTRY,
        **AGENTIC_MEMORY_TOOLS_REGISTRY,
        **MEMORY_TOOLS_REGISTRY,
        'ListIndexTool': {...},   # ~35 inline core/cat/search-relevance tools
        ...
    }

That order is observable (it determines ``tools/list`` ordering and is pinned by
tests). This module makes the order an explicit, reviewable manifest instead of
an implicit consequence of literal position, and routes composition through
``ToolRegistry.add`` so duplicate keys fail loud.

Faithful by construction: ``compose_registry`` pulls from the *same* sub-registry
objects the legacy literal spreads, so the composed catalog is identical
key-for-key and value-for-value to ``tools.TOOL_REGISTRY``. A pinning test
(:mod:`tests.tools.test_modules`) asserts that equivalence for memory on and off.

Later phases replace each ``dict`` sub-registry with a per-domain
``register(registry, ctx)`` module; the manifest order stays the contract.
"""

from typing import Any, Mapping


# The canonical group order, matching the legacy ``**``-spread in tools.py:
#   skills -> agentic_memory -> memory -> (inline core/cat/search-relevance)
# Each entry is (group_name, "how to source it"). The inline group is sourced
# from tools.TOOL_REGISTRY minus the three sub-registries, preserving its order.
GROUP_ORDER: tuple[str, ...] = (
    'skills',
    'agentic_memory',
    'memory',
    'core',  # core + cat + search-relevance + generic + list-clusters (legacy inline block)
)


def compose_registry(
    *,
    skills: Mapping[str, Any],
    agentic_memory: Mapping[str, Any],
    memory: Mapping[str, Any],
    core: Mapping[str, Any],
):
    """Compose the full tool registry in canonical group order.

    Args:
        skills: The skills tools sub-registry (DataDistribution, LogPatternAnalysis).
        agentic_memory: The agentic-memory tools sub-registry (7 ML-Commons tools).
        memory: The memory tools sub-registry (3 tools; empty unless enabled).
        core: The inline core/cat/search-relevance/generic/list-clusters block,
            in its legacy declaration order.

    Returns:
        ToolRegistry: An insertion-ordered registry equal key-for-key to the
        legacy ``tools.TOOL_REGISTRY`` for the same inputs. Raises
        ``DuplicateToolError`` if any key collides across groups.
    """
    from .registry import ToolRegistry

    registry = ToolRegistry()
    groups = {
        'skills': skills,
        'agentic_memory': agentic_memory,
        'memory': memory,
        'core': core,
    }
    for group_name in GROUP_ORDER:
        registry.update(dict(groups[group_name]))
    return registry

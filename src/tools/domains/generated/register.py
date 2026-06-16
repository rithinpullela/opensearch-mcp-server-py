# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Static ToolSpecs for the 4 formerly-OpenAPI-generated tools.

Assembles ``MsearchTool``, ``ExplainTool``, ``CountTool``, and ``ClusterHealthTool``
from the hand-built schemas (``schema.py``), validation models (``params.py``), and
the ported request handlers (``handlers.py``). The resulting specs reproduce exactly
what ``tool_generator`` produced at boot — same display names, ``input_schema``,
``min_version='1.0'``, ``max_version='99.99.99'``, and ``http_methods`` strings —
verified against ``tests/fixtures/generated_tools_golden.json``.

``build_generated_tools()`` returns the four specs as an ordered dict keyed by
canonical tool name, ready to fold into the registry. The version-compatibility
gate is injected (defaulting to ``tools.check_tool_compatibility``) so the handlers
stay decoupled from the registry module.
"""

from . import handlers as _handlers
from . import params as _params
from . import schema as _schema
from typing import Any, Awaitable, Callable


# Metadata captured from the live generator (golden snapshot). The version strings
# are the raw spec values ('1.0', not '1.0.0') and must not be normalized.
_MIN_VERSION = '1.0'
_MAX_VERSION = '99.99.99'

# Descriptions the generator emitted (the description of each operation group's first
# endpoint in the OpenSearch API spec). Inlined here as the single source of truth;
# the golden-snapshot test asserts they still match the captured generator output.
_DESCRIPTIONS = {
    'MsearchTool': 'Allows to execute several search operations in one request.',
    'ExplainTool': (
        "Returns information about why a specific document matches (or doesn't match) a query."
    ),
    'CountTool': 'Returns number of documents matching a query.',
    'ClusterHealthTool': 'Returns basic information about the health of the cluster.',
}


# The single source of truth for generated-tool order. This is the exact order the
# old runtime generator appended the tools to TOOL_REGISTRY: it iterated SPEC_FILES
# = ['cluster.yaml', '_core.yaml'] and, within each, the spec's operation order —
# yielding ClusterHealth (from cluster.yaml), then Count, Msearch, Explain (from
# _core.yaml). Verified empirically against the live generator before deletion.
# `tests/tools/domains/test_generated_tools_golden.py` and the registry tail-order
# test pin this; do not reorder without updating those.
GENERATED_TOOL_ORDER = ('ClusterHealthTool', 'CountTool', 'MsearchTool', 'ExplainTool')


def build_generated_tools(
    version_check: Callable[[str, Any], Awaitable[None]],
) -> dict[str, dict]:
    """Build the 4 static generated-tool specs in the generator's exact order.

    Args:
        version_check: The compatibility gate injected into each handler — the same
            callable the generated ``tool_func`` used
            (``tools.check_tool_compatibility``). Required (no default) to avoid an
            import cycle with ``tools.tools`` and an untested fallback branch.

    Returns:
        An ordered ``dict`` mapping canonical tool name -> ToolSpec, keyed in
        :data:`GENERATED_TOOL_ORDER` (the order the old generator produced).
    """
    descriptions = _DESCRIPTIONS

    # Per-tool spec pieces, assembled below in GENERATED_TOOL_ORDER.
    pieces = {
        'ClusterHealthTool': (
            _schema.CLUSTER_HEALTH_SCHEMA,
            _handlers.ENDPOINTS_CLUSTER_HEALTH,
            _params.ClusterHealthArgs,
            'GET',
        ),
        'CountTool': (
            _schema.COUNT_SCHEMA,
            _handlers.ENDPOINTS_COUNT,
            _params.CountArgs,
            'GET, POST',
        ),
        'MsearchTool': (
            _schema.MSEARCH_SCHEMA,
            _handlers.ENDPOINTS_MSEARCH,
            _params.MsearchArgs,
            'GET, POST',
        ),
        'ExplainTool': (
            _schema.EXPLAIN_SCHEMA,
            _handlers.ENDPOINTS_EXPLAIN,
            _params.ExplainArgs,
            'GET, POST',
        ),
    }

    specs: dict[str, dict] = {}
    for name in GENERATED_TOOL_ORDER:
        input_schema, endpoints, args_model, http_methods = pieces[name]
        specs[name] = {
            'display_name': name,
            'description': descriptions[name],
            'input_schema': input_schema,
            'function': _handlers.make_handler(name, endpoints, version_check),
            'args_model': args_model,
            'min_version': _MIN_VERSION,
            'max_version': _MAX_VERSION,
            'http_methods': http_methods,
        }

    return specs

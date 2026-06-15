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
from typing import Any, Awaitable, Callable, Optional


# Metadata captured from the live generator (golden snapshot). The version strings
# are the raw spec values ('1.0', not '1.0.0') and must not be normalized.
_MIN_VERSION = '1.0'
_MAX_VERSION = '99.99.99'


def _descriptions() -> dict[str, str]:
    """Return the per-tool description strings the generator emitted.

    The generator used the description of the first endpoint in each operation
    group. These are captured in the golden snapshot; sourced from there at build
    time so they cannot drift.
    """
    import json
    from pathlib import Path

    # The snapshot lives under tests/fixtures; resolve relative to the repo root.
    # We read descriptions from it so this module is the single place that needs the
    # text, and the lock test guarantees they match.
    fixture = Path(__file__).resolve()
    for parent in fixture.parents:
        candidate = parent / 'tests' / 'fixtures' / 'generated_tools_golden.json'
        if candidate.exists():
            data = json.loads(candidate.read_text())
            return {k: v['description'] for k, v in data.items()}
    raise FileNotFoundError('generated_tools_golden.json not found for descriptions')


def build_generated_tools(
    version_check: Optional[Callable[[str, Any], Awaitable[None]]] = None,
) -> dict[str, dict]:
    """Build the 4 static generated-tool specs in canonical order.

    Args:
        version_check: The compatibility gate to inject into each handler. Defaults
            to ``tools.check_tool_compatibility`` (the same callable the generated
            ``tool_func`` used).

    Returns:
        An ordered ``dict`` mapping canonical tool name -> ToolSpec dict, for
        ``Msearch``/``Explain``/``Count``/``ClusterHealth`` (the generator's order).
    """
    if version_check is None:
        from tools.tools import check_tool_compatibility as version_check

    descriptions = _descriptions()

    specs: dict[str, dict] = {}

    specs['MsearchTool'] = {
        'display_name': 'MsearchTool',
        'description': descriptions['MsearchTool'],
        'input_schema': _schema.MSEARCH_SCHEMA,
        'function': _handlers.make_handler(
            'MsearchTool', _handlers.ENDPOINTS_MSEARCH, version_check
        ),
        'args_model': _params.MsearchArgs,
        'min_version': _MIN_VERSION,
        'max_version': _MAX_VERSION,
        'http_methods': 'GET, POST',
    }
    specs['ExplainTool'] = {
        'display_name': 'ExplainTool',
        'description': descriptions['ExplainTool'],
        'input_schema': _schema.EXPLAIN_SCHEMA,
        'function': _handlers.make_handler(
            'ExplainTool', _handlers.ENDPOINTS_EXPLAIN, version_check
        ),
        'args_model': _params.ExplainArgs,
        'min_version': _MIN_VERSION,
        'max_version': _MAX_VERSION,
        'http_methods': 'GET, POST',
    }
    specs['CountTool'] = {
        'display_name': 'CountTool',
        'description': descriptions['CountTool'],
        'input_schema': _schema.COUNT_SCHEMA,
        'function': _handlers.make_handler('CountTool', _handlers.ENDPOINTS_COUNT, version_check),
        'args_model': _params.CountArgs,
        'min_version': _MIN_VERSION,
        'max_version': _MAX_VERSION,
        'http_methods': 'GET, POST',
    }
    specs['ClusterHealthTool'] = {
        'display_name': 'ClusterHealthTool',
        'description': descriptions['ClusterHealthTool'],
        'input_schema': _schema.CLUSTER_HEALTH_SCHEMA,
        'function': _handlers.make_handler(
            'ClusterHealthTool', _handlers.ENDPOINTS_CLUSTER_HEALTH, version_check
        ),
        'args_model': _params.ClusterHealthArgs,
        'min_version': _MIN_VERSION,
        'max_version': _MAX_VERSION,
        'http_methods': 'GET',
    }

    return specs

# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Hand-built input schemas for the 4 formerly-OpenAPI-generated tools.

Background
----------
``MsearchTool``, ``ExplainTool``, ``CountTool``, and ``ClusterHealthTool`` used to
be synthesized at boot by fetching the OpenSearch OpenAPI spec from GitHub
(``tool_generator.py``). That runtime network fetch is being removed; these four
tools become static. Their ``input_schema`` dicts must reproduce what the
generator produced (**semantically** — dict-equal, see fidelity note), because the schema is part of the wire
contract and is locked by a golden snapshot
(``tests/fixtures/generated_tools_golden.json``).

How fidelity is guaranteed
--------------------------
The generator built each schema as ``baseToolArgs``' JSON-schema properties plus
a few tool-specific properties (``index``/``id``/``body``). We reconstruct exactly
that: start from ``baseToolArgs.model_json_schema()['properties']`` (the same
source the generator used, so those 11 properties are byte-identical) and add the
tool-specific properties with the same shapes the generator emitted:

* ``index`` / ``id``  -> ``{'title': <Name>.title(), 'type': 'string'}``
* ``body``            -> ``{'title': 'Body', 'description': <BODY_DESCRIPTION>}``
  (note: **no** ``type`` key — matching the generator, which omitted it for the
  body parameter)

Fidelity scope: ``tests/tools/domains/test_generated_tools_golden.py`` asserts the
``input_schema`` is **dict-equal** (order-insensitive) to the captured snapshot, and
that ``display_name`` / ``description`` / ``http_methods`` / versions match exactly. The
property *insertion order* here is hand-matched to the generator's (base props, then
path params in URL order, then body last) but is NOT enforced by the oracle — JSON
Schema treats object properties and ``required`` as unordered, so order is semantically
inert. The snapshot was stored with sorted keys; do not read "byte-for-byte" into it.
"""

from copy import deepcopy
from tools.tool_params import baseToolArgs
from typing import Any


# Body descriptions, verbatim from tool_generator.BODY_DESCRIPTIONS (+ the generic
# 'Request body' fallback the generator used when an op had no specific entry).
_MSEARCH_BODY_DESCRIPTION = (
    'Request body as NDJSON format: alternating lines of header and query objects '
    'ending with \\n. Alternatively, pass a JSON array [header, query, header, '
    'query, ...] and the tool will convert it to NDJSON for you.'
)
_EXPLAIN_BODY_DESCRIPTION = 'Request body containing the query to explain.'
_COUNT_BODY_DESCRIPTION = 'Request body'


def _base_properties() -> dict[str, Any]:
    """Return a deep copy of baseToolArgs' JSON-schema properties (11 fields).

    Deep-copied so callers can mutate their schema without touching the shared
    Pydantic-derived dict.
    """
    return deepcopy(baseToolArgs.model_json_schema().get('properties', {}))


def _string_param(name: str) -> dict[str, str]:
    """Build a path-parameter property exactly as the generator did.

    The generator emitted ``{'title': name.title(), 'type': 'string'}`` for path
    parameters like ``index`` and ``id``.
    """
    return {'title': name.title(), 'type': 'string'}


def _body_param(description: str) -> dict[str, str]:
    """Build the ``body`` property exactly as the generator did (no ``type`` key)."""
    return {'title': 'Body', 'description': description}


def _build_schema(
    title: str,
    *,
    extra_properties: dict[str, Any],
    required: list[str] | None,
) -> dict[str, Any]:
    """Assemble a generated-tool input_schema in the generator's exact shape.

    Property insertion order matches the generator: base properties first, then
    the tool-specific ones. ``required`` is included only when non-empty (the
    generator omitted the key entirely when there were no required fields).
    """
    properties = _base_properties()
    properties.update(extra_properties)
    schema: dict[str, Any] = {'type': 'object', 'title': title, 'properties': properties}
    if required:
        schema['required'] = required
    return schema


MSEARCH_SCHEMA = _build_schema(
    'MsearchArgs',
    extra_properties={
        'body': _body_param(_MSEARCH_BODY_DESCRIPTION),
        'index': _string_param('index'),
    },
    required=['body'],
)

EXPLAIN_SCHEMA = _build_schema(
    'ExplainArgs',
    # Property insertion order matches the generator exactly: path params (index, id)
    # in URL order, then body last. (Order is semantically insignificant in JSON
    # Schema, but we preserve it so the schema is byte-faithful, not just dict-equal.)
    extra_properties={
        'index': _string_param('index'),
        'id': _string_param('id'),
        'body': _body_param(_EXPLAIN_BODY_DESCRIPTION),
    },
    required=['body', 'id', 'index'],
)

COUNT_SCHEMA = _build_schema(
    'CountArgs',
    extra_properties={
        'body': _body_param(_COUNT_BODY_DESCRIPTION),
        'index': _string_param('index'),
    },
    required=None,
)

CLUSTER_HEALTH_SCHEMA = _build_schema(
    'ClusterHealthArgs',
    extra_properties={'index': _string_param('index')},
    required=None,
)

# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tool version-compatibility gate (leaf module).

Houses ``check_tool_compatibility`` — the per-call check that a tool is supported
by the connected OpenSearch cluster's version. It lived in ``tools.py``, which
created an import cycle (``tools`` → ``generic_api_tool`` → ``tool_filter`` →
``tools``) that was worked around with lazy in-function imports. Moving it to a
leaf module that takes the registry explicitly breaks that cycle.

The error message and raising behavior are reproduced **byte-for-byte** from the
original (`tools.py`), because the text surfaces to MCP clients and is asserted by
the integration oracle. ``tools.check_tool_compatibility`` now delegates here, so
its ~40 call sites are unchanged.

Version-fetch caching (per the rebuild design) is layered inside
``get_opensearch_version`` in a later phase; this module is unaffected by that —
it just awaits whatever ``version_fetcher`` returns.
"""

from .tool_params import baseToolArgs
from .utils import is_tool_compatible
from typing import Any, Awaitable, Callable, Mapping, Optional


def build_version_unsupported_message(
    tool_display_name: str,
    opensearch_version: Optional[str],
    min_version: str,
    max_version: str,
) -> str:
    """Build the exact 'tool not supported for this version' error string.

    Extracted so the message can be unit-tested independently and reused. The
    format is contract — it is asserted via the ``Error <op>: <exc>`` text that
    integration tests match — do not reword it.
    """
    version_info = (
        f'{min_version} to {max_version}'
        if min_version and max_version
        else f'{min_version} or later'
        if min_version
        else f'up to {max_version}'
        if max_version
        else None
    )

    error_message = (
        f"Tool '{tool_display_name}' is not supported for this OpenSearch version "
        f'(current version: {opensearch_version}).'
    )
    if version_info:
        error_message += f' Supported version: {version_info}.'
    return error_message


async def check_tool_compatibility(
    tool_name: str,
    registry: Mapping[str, Any],
    version_fetcher: Callable[[Optional[baseToolArgs]], Awaitable[Optional[str]]],
    args: Optional[baseToolArgs] = None,
) -> None:
    """Raise if ``tool_name`` is incompatible with the cluster's OpenSearch version.

    Args:
        tool_name: Canonical registry key of the tool being invoked.
        registry: The tool registry (anything dict-like keyed by tool name).
        version_fetcher: Async callable returning the cluster version string (or
            ``None`` on error / serverless), given the tool args. Injected so this
            module does not import the opensearch client (cycle-free, testable).
        args: The tool's parsed args, forwarded to ``version_fetcher``.

    Raises:
        Exception: With the exact legacy message when the tool is not compatible.
            (Bare ``Exception`` is preserved for byte-identical behavior; a typed
            ``ToolVersionIncompatibleError`` is a tracked follow-up — see
            REBUILD_MASTER_PLAN.md — and must subclass ``Exception``.)
    """
    opensearch_version = await version_fetcher(args)
    tool_info = registry[tool_name]
    if not is_tool_compatible(opensearch_version, tool_info):
        tool_display_name = tool_info.get('display_name', tool_name)
        min_version = tool_info.get('min_version', '')
        max_version = tool_info.get('max_version', '')
        raise Exception(
            build_version_unsupported_message(
                tool_display_name, opensearch_version, min_version, max_version
            )
        )

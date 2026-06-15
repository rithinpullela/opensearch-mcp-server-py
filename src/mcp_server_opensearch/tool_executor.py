# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared tool execution with structured logging for metrics.

Extracts the duplicated call_tool() logic from stdio_server.py and
streaming_server.py into a single function that wraps tool invocation
with timing, error detection, and structured metric event logging.

Emits a structured log event (event_type="tool_execution") for every
tool invocation, enabling metric filters for:
- Tool execution failure alarms
- Invocation counts by tool name
- Execution latency by tool name
- Error rates by error type and tool
"""

import logging
import time
from mcp.types import CallToolResult, TextContent


logger = logging.getLogger(__name__)


async def execute_tool(
    name: str,
    arguments: dict,
    enabled_tools: dict,
) -> list[TextContent] | CallToolResult:
    """Execute an MCP tool with structured logging for metrics.

    Resolves the tool by display name, validates arguments, executes,
    and emits a structured log event with timing and status information.

    Args:
        name: The display name of the tool as seen by the MCP client.
        arguments: The raw argument dict from the MCP protocol.
        enabled_tools: The enabled tools registry dict.

    Returns:
        On success, the tool's result content list. On a tool-execution failure
        (a soft error carrying ``is_error``), a ``CallToolResult`` with
        ``isError=True`` so spec-compliant MCP clients can detect the failure — the
        low-level SDK passes that flag through to the wire. The error message text is
        unchanged and still appears in ``content[0].text``.

    Raises:
        ValueError: If the tool name is unknown or disabled (pre-invocation errors
            raise and the SDK already surfaces them as ``isError=True``).
    """
    start_time = time.monotonic()
    status = 'success'
    error_type = None
    found_tool_key = None

    try:
        # Resolve tool by display name
        for key, tool_info in enabled_tools.items():
            if tool_info.get('display_name', key) == name:
                found_tool_key = key
                break

        if not found_tool_key:
            status = 'error'
            error_type = 'UnknownToolError'
            raise ValueError(f'Unknown or disabled tool: {name}')

        tool = enabled_tools[found_tool_key]
        from tools.tool_params import validate_args_for_mode

        parsed = validate_args_for_mode(arguments, tool['args_model'])
        result = await tool['function'](parsed)

        # Detect soft errors: tools catch exceptions internally and
        # return errors via log_tool_error(), which sets is_error=True
        # on the response dict as an explicit status indicator.
        if result and len(result) > 0:
            if isinstance(result[0], dict) and result[0].get('is_error'):
                status = 'error'
                # Surface the failure on the wire: a bare list would be serialized by
                # the SDK as CallToolResult(isError=False), making every tool error look
                # like a success to spec-compliant clients. Returning CallToolResult with
                # isError=True is passed through verbatim by the low-level server; the
                # content (incl. the exact 'Error <op>: <exc>' text and the legacy
                # is_error key) is preserved.
                return CallToolResult(content=result, isError=True)

        return result

    except ValueError:
        # For unknown tool, status/error_type were already set above.
        # For validation errors (from validate_args_for_mode), set them now.
        if status != 'error':
            status = 'error'
            error_type = 'ValidationError'
        raise

    except Exception as e:
        status = 'error'
        error_type = type(e).__name__
        raise

    finally:
        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        log_extra: dict[str, object] = {
            'event_type': 'tool_execution',
            'tool_name': name,
            'status': status,
            'duration_ms': duration_ms,
        }
        if found_tool_key:
            log_extra['tool_key'] = found_tool_key
        if error_type:
            log_extra['error_type'] = error_type

        if status == 'success':
            logger.info(
                f'Tool executed: {name} ({duration_ms}ms)',
                extra=log_extra,
            )
        else:
            logger.error(
                f'Tool execution failed: {name} ({duration_ms}ms)',
                extra=log_extra,
            )

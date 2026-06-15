# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Request handlers for the 4 static (ex-generated) tools.

Ports the execution path of the former ``tool_generator.tool_func`` **verbatim** so
the four tools behave byte-for-byte as they did when synthesized from the OpenAPI
spec:

* ``process_body`` — NDJSON conversion for msearch; JSON parse for others. Copied
  exactly (the msearch NDJSON spacing is load-bearing).
* ``select_endpoint`` — picks the endpoint by how many path params have values;
  **ignores HTTP method**, so body-bearing tools issue GET-with-body. Copied exactly.
* the handler — extracts base args (missing -> ``''``), opens the client, runs the
  version gate, processes body, selects endpoint, fills path params, and calls
  ``transport.perform_request(method, url, params=query, body=body)``. The response
  is returned as ``TextContent`` via plain ``json.dumps`` (NOT the compact
  ``format_json``) — preserving the generator's exact serialization.

Endpoint tables are hard-coded from the pinned OpenSearch API spec (captured in the
golden snapshot); they no longer require a boot-time network fetch.
"""

import json
from mcp.types import TextContent
from tools.tool_logging import log_tool_error
from tools.tool_params import baseToolArgs
from typing import Any, Awaitable, Callable


# --- Endpoint tables (from the pinned spec; method order preserved) ---
ENDPOINTS_MSEARCH = [
    {'path': '/_msearch', 'method': 'get'},
    {'path': '/_msearch', 'method': 'post'},
    {'path': '/{index}/_msearch', 'method': 'get'},
    {'path': '/{index}/_msearch', 'method': 'post'},
]
ENDPOINTS_EXPLAIN = [
    {'path': '/{index}/_explain/{id}', 'method': 'get'},
    {'path': '/{index}/_explain/{id}', 'method': 'post'},
]
ENDPOINTS_COUNT = [
    {'path': '/_count', 'method': 'get'},
    {'path': '/_count', 'method': 'post'},
    {'path': '/{index}/_count', 'method': 'get'},
    {'path': '/{index}/_count', 'method': 'post'},
]
ENDPOINTS_CLUSTER_HEALTH = [
    {'path': '/_cluster/health', 'method': 'get'},
    {'path': '/_cluster/health/{index}', 'method': 'get'},
]


def process_body(body: Any, tool_name: str) -> Any:
    """Process a request body for a tool (ported verbatim from tool_generator).

    For ``MsearchTool`` the body is converted to NDJSON (a JSON-array string or list
    becomes newline-delimited objects; an NDJSON string is passed through with a
    trailing newline ensured). For other tools a JSON string is parsed to an object.

    Args:
        body: The raw request body (str, list, dict, or None).
        tool_name: The canonical tool name (e.g. ``'MsearchTool'``).

    Returns:
        The processed body in the form the OpenSearch transport expects.

    Raises:
        ValueError: If a non-msearch string body is not valid JSON.
    """
    if body is None:
        return None

    # Handle string body
    if isinstance(body, str):
        # Multi search tool (msearch) requires request body to be in NDJSON format
        if tool_name == 'MsearchTool':
            try:
                # Check if it's a JSON array string
                parsed = json.loads(body)
                if isinstance(parsed, list):
                    # Convert JSON array to NDJSON format
                    return ''.join(json.dumps(item) + '\n' for item in parsed)
            except json.JSONDecodeError:
                pass  # Fall through to treat as NDJSON
            # Treat as NDJSON string - ensure it ends with newline
            return body if body.endswith('\n') else body + '\n'

        # For other tools, parse JSON string to object
        if body.strip():
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                raise ValueError(f'Invalid JSON in body parameter: {str(body)[:100]}...')
        return None

    # Handle non-string body (list, dict, etc.)
    if isinstance(body, list) and tool_name == 'MsearchTool':
        # Direct JSON array (from MCP tools)
        return ''.join(json.dumps(item) + '\n' for item in body)

    return body


def select_endpoint(endpoints: list[dict], params: dict) -> dict:
    """Select the most appropriate endpoint based on available params (verbatim).

    Sorts endpoints by how many of their path parameters have valid values and
    returns the first whose path parameters are all satisfied; otherwise falls back
    to the simplest (no path params) endpoint or the first one. HTTP method is not
    considered — body-bearing tools therefore issue GET-with-body, matching the
    generator.
    """
    # Filter out empty or None values from params
    valid_params = {k: v for k, v in params.items() if v not in (None, '', {}, [])}

    # Sort endpoints by number of path parameters that have valid values
    sorted_endpoints = sorted(
        endpoints,
        key=lambda ep: sum(
            1
            for p in ep['path'].split('/')
            if p.startswith('{') and p.endswith('}') and p[1:-1] in valid_params
        ),
        reverse=True,
    )

    # Return the first endpoint where all required path parameters have valid values
    for endpoint in sorted_endpoints:
        path_params = [
            p[1:-1] for p in endpoint['path'].split('/') if p.startswith('{') and p.endswith('}')
        ]
        if all(param in valid_params for param in path_params):
            return endpoint

    # Fall back to simplest endpoint or first endpoint
    return next(
        (ep for ep in endpoints if not any('{' in p for p in ep['path'].split('/'))), endpoints[0]
    )


def _path_parameters(endpoints: list[dict]) -> set[str]:
    """Collect the set of path-parameter names appearing across ``endpoints``."""
    names: set[str] = set()
    for endpoint in endpoints:
        for part in endpoint['path'].split('/'):
            if part.startswith('{') and part.endswith('}'):
                names.add(part[1:-1])
    return names


def make_handler(
    tool_name: str,
    endpoints: list[dict],
    version_check: Callable[[str, baseToolArgs], Awaitable[None]],
) -> Callable[[Any], Awaitable[list]]:
    """Build the async handler for a static generated tool.

    Reproduces ``tool_generator.tool_func`` exactly: base-arg extraction (missing
    fields default to ``''``), client open, version gate, body processing, endpoint
    selection, path-param substitution, GET/POST-with-body request, and a
    ``TextContent`` response serialized with plain ``json.dumps``.

    Args:
        tool_name: Canonical tool name (e.g. ``'MsearchTool'``); also drives the
            msearch-specific NDJSON branch in ``process_body``.
        endpoints: The endpoint table for this tool.
        version_check: The compatibility gate (injected; same callable
            ``tools.check_tool_compatibility`` the generator used).

    Returns:
        An async function taking the tool's args model and returning MCP content.
    """
    path_parameters = _path_parameters(endpoints)

    async def handler(params: Any) -> list:
        try:
            from opensearch.client import get_opensearch_client

            params_dict = params.model_dump() if hasattr(params, 'model_dump') else {}

            try:
                # Extract all baseToolArgs fields from params_dict
                base_args = {}
                base_fields = baseToolArgs.model_fields.keys()
                for field in base_fields:
                    if field in params_dict:
                        base_args[field] = params_dict.pop(field)
                    else:
                        # Provide default empty string for required fields in single mode
                        base_args[field] = ''

                args = baseToolArgs(**base_args)
            except Exception as e:
                return log_tool_error(tool_name, e, 'initializing OpenSearch client')

            # Use context manager to ensure proper client cleanup
            async with get_opensearch_client(args) as request_client:
                await version_check(tool_name, args)
                # Process body and select endpoint
                body = process_body(params_dict.pop('body', None), tool_name)
                selected_endpoint = select_endpoint(endpoints, params_dict)

                # Prepare request
                formatted_path = selected_endpoint['path']
                for param_name in path_parameters:
                    if param_name in params_dict:
                        formatted_path = formatted_path.replace(
                            f'{{{param_name}}}', str(params_dict[param_name])
                        )
                        del params_dict[param_name]
                method = selected_endpoint['method'].upper()  # HTTP method (GET, POST, etc.)
                api_path = f'/{formatted_path.lstrip("/")}'  # Ensure path starts with /

                # Execute the OpenSearch API request
                response = await request_client.transport.perform_request(
                    method=method, url=api_path, params=params_dict, body=body
                )

                return [
                    TextContent(
                        type='text',
                        text=json.dumps(response) if not isinstance(response, str) else response,
                    )
                ]

        except Exception as e:
            return log_tool_error(tool_name, e, f'executing {tool_name}')

    return handler

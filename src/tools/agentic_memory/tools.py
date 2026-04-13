# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
from typing import Dict, Any
from urllib.parse import quote
from tools.tool_logging import log_tool_error
from tools.utils import is_tool_compatible
from opensearch.client import get_opensearch_client
from .params import (
    AddAgenticMemoriesArgs,
    CreateAgenticMemorySessionArgs,
    DeleteAgenticMemoryByIDArgs,
    DeleteAgenticMemoryByQueryArgs,
    GetAgenticMemoryArgs,
    SearchAgenticMemoryArgs,
    UpdateAgenticMemoryArgs,
)


# ---------------------------------------------------------------------------
# Helpers — "dumb pipes" to OpenSearch (no try/except)
# ---------------------------------------------------------------------------


async def create_agentic_memory_session(
    args: CreateAgenticMemorySessionArgs,
) -> Dict[str, Any]:
    """Create a new agentic memory session in the specified memory container."""
    async with get_opensearch_client(args) as client:
        url = '/'.join([
            '/_plugins/_ml/memory_containers',
            quote(args.memory_container_id, safe=''),
            'memories/sessions',
        ])
        body = args.model_dump(
            exclude={'memory_container_id', 'opensearch_cluster_name'},
            exclude_none=True,
        )
        return await client.transport.perform_request(method='POST', url=url, body=body)


async def add_agentic_memories(args: AddAgenticMemoriesArgs) -> Dict[str, Any]:
    """Add agentic memories to the specified memory container."""
    async with get_opensearch_client(args) as client:
        url = '/'.join([
            '/_plugins/_ml/memory_containers',
            quote(args.memory_container_id, safe=''),
            'memories',
        ])
        body = args.model_dump(
            exclude={'memory_container_id', 'opensearch_cluster_name'},
            exclude_none=True,
            by_alias=True,
        )
        return await client.transport.perform_request(method='POST', url=url, body=body)


async def get_agentic_memory(args: GetAgenticMemoryArgs) -> Dict[str, Any]:
    """Retrieve a specific agentic memory by its type and ID."""
    async with get_opensearch_client(args) as client:
        url = '/'.join([
            '/_plugins/_ml/memory_containers',
            quote(args.memory_container_id, safe=''),
            'memories',
            quote(args.memory_type, safe=''),
            quote(args.id, safe=''),
        ])
        return await client.transport.perform_request(method='GET', url=url)


async def update_agentic_memory(args: UpdateAgenticMemoryArgs) -> Dict[str, Any]:
    """Update a specific agentic memory by its type and ID."""
    async with get_opensearch_client(args) as client:
        url = '/'.join([
            '/_plugins/_ml/memory_containers',
            quote(args.memory_container_id, safe=''),
            'memories',
            quote(args.memory_type, safe=''),
            quote(args.id, safe=''),
        ])
        body = args.model_dump(
            exclude={'memory_container_id', 'memory_type', 'id', 'opensearch_cluster_name'},
            exclude_none=True,
            by_alias=True,
        )
        return await client.transport.perform_request(method='PUT', url=url, body=body)


async def delete_agentic_memory_by_id(args: DeleteAgenticMemoryByIDArgs) -> Dict[str, Any]:
    """Delete a specific agentic memory by its type and ID."""
    async with get_opensearch_client(args) as client:
        url = '/'.join([
            '/_plugins/_ml/memory_containers',
            quote(args.memory_container_id, safe=''),
            'memories',
            quote(args.memory_type, safe=''),
            quote(args.id, safe=''),
        ])
        return await client.transport.perform_request(method='DELETE', url=url)


async def delete_agentic_memory_by_query(args: DeleteAgenticMemoryByQueryArgs) -> Dict[str, Any]:
    """Delete agentic memories matching the provided query."""
    async with get_opensearch_client(args) as client:
        url = '/'.join([
            '/_plugins/_ml/memory_containers',
            quote(args.memory_container_id, safe=''),
            'memories',
            quote(args.memory_type, safe=''),
            '_delete_by_query',
        ])
        body = args.model_dump(
            exclude={'memory_container_id', 'memory_type', 'opensearch_cluster_name'},
            exclude_none=True,
        )
        return await client.transport.perform_request(method='POST', url=url, body=body)


async def search_agentic_memory(args: SearchAgenticMemoryArgs) -> Dict[str, Any]:
    """Search for agentic memories using OpenSearch query DSL."""
    async with get_opensearch_client(args) as client:
        url = '/'.join([
            '/_plugins/_ml/memory_containers',
            quote(args.memory_container_id, safe=''),
            'memories',
            quote(args.memory_type, safe=''),
            '_search',
        ])
        body = args.model_dump(
            exclude={'memory_container_id', 'memory_type', 'opensearch_cluster_name'},
            exclude_none=True,
        )
        return await client.transport.perform_request(method='GET', url=url, body=body)


# ---------------------------------------------------------------------------
# Tool functions — try/except + log_tool_error (the one place errors are caught)
# ---------------------------------------------------------------------------


async def check_tool_compatibility(tool_name: str, args):
    """Check if a tool is compatible with the cluster version."""
    from tools.tools import TOOL_REGISTRY
    compatible, message = await is_tool_compatible(tool_name, TOOL_REGISTRY, args)
    if not compatible:
        raise Exception(message)


async def create_agentic_memory_session_tool(args: CreateAgenticMemorySessionArgs) -> list[dict]:
    """Tool to create a new session in an agentic memory container."""
    try:
        await check_tool_compatibility('CreateAgenticMemorySessionTool', args)
        result = await create_agentic_memory_session(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Session created:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('CreateAgenticMemorySessionTool', e, 'creating session')


async def add_agentic_memories_tool(args: AddAgenticMemoriesArgs) -> list[dict]:
    """Tool to add memories to an agentic memory container."""
    try:
        await check_tool_compatibility('AddAgenticMemoriesTool', args)
        result = await add_agentic_memories(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Memories added:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('AddAgenticMemoriesTool', e, 'adding memories')


async def get_agentic_memory_tool(args: GetAgenticMemoryArgs) -> list[dict]:
    """Tool to retrieve a specific agentic memory by type and ID."""
    try:
        await check_tool_compatibility('GetAgenticMemoryTool', args)
        result = await get_agentic_memory(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Memory retrieved:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('GetAgenticMemoryTool', e, 'retrieving memory')


async def update_agentic_memory_tool(args: UpdateAgenticMemoryArgs) -> list[dict]:
    """Tool to update a specific agentic memory by type and ID."""
    try:
        await check_tool_compatibility('UpdateAgenticMemoryTool', args)
        result = await update_agentic_memory(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Memory updated:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('UpdateAgenticMemoryTool', e, 'updating memory')


async def delete_agentic_memory_by_id_tool(args: DeleteAgenticMemoryByIDArgs) -> list[dict]:
    """Tool to delete a specific agentic memory by type and ID."""
    try:
        await check_tool_compatibility('DeleteAgenticMemoryByIDTool', args)
        result = await delete_agentic_memory_by_id(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Memory deleted:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('DeleteAgenticMemoryByIDTool', e, 'deleting memory')


async def delete_agentic_memory_by_query_tool(args: DeleteAgenticMemoryByQueryArgs) -> list[dict]:
    """Tool to delete agentic memories by query."""
    try:
        await check_tool_compatibility('DeleteAgenticMemoryByQueryTool', args)
        result = await delete_agentic_memory_by_query(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Memories deleted by query:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('DeleteAgenticMemoryByQueryTool', e, 'deleting memories by query')


async def search_agentic_memory_tool(args: SearchAgenticMemoryArgs) -> list[dict]:
    """Tool to search memories within an agentic memory container."""
    try:
        await check_tool_compatibility('SearchAgenticMemoryTool', args)
        result = await search_agentic_memory(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Memory search results:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('SearchAgenticMemoryTool', e, 'searching memories')


# ---------------------------------------------------------------------------
# Registry — spread into TOOL_REGISTRY via **AGENTIC_MEMORY_TOOLS_REGISTRY
# ---------------------------------------------------------------------------

AGENTIC_MEMORY_TOOLS_REGISTRY = {
    'CreateAgenticMemorySessionTool': {
        'display_name': 'CreateAgenticMemorySessionTool',
        'description': 'Creates a new session in an agentic memory container. Sessions group related memories together and can include metadata and namespace information.',
        'input_schema': CreateAgenticMemorySessionArgs.model_json_schema(),
        'function': create_agentic_memory_session_tool,
        'args_model': CreateAgenticMemorySessionArgs,
        'min_version': '3.3.0',
        'http_methods': 'POST',
    },
    'AddAgenticMemoriesTool': {
        'display_name': 'AddAgenticMemoriesTool',
        'description': 'Adds memories to an agentic memory container. Supports conversational payloads (message lists) and data payloads (structured data). Optionally uses an LLM to extract key information.',
        'input_schema': AddAgenticMemoriesArgs.model_json_schema(),
        'function': add_agentic_memories_tool,
        'args_model': AddAgenticMemoriesArgs,
        'min_version': '3.3.0',
        'http_methods': 'POST',
    },
    'GetAgenticMemoryTool': {
        'display_name': 'GetAgenticMemoryTool',
        'description': 'Retrieves a specific agentic memory by its type and ID from a memory container.',
        'input_schema': GetAgenticMemoryArgs.model_json_schema(),
        'function': get_agentic_memory_tool,
        'args_model': GetAgenticMemoryArgs,
        'min_version': '3.3.0',
        'http_methods': 'GET',
    },
    'UpdateAgenticMemoryTool': {
        'display_name': 'UpdateAgenticMemoryTool',
        'description': 'Updates a specific agentic memory by its type and ID. Supports updating sessions (summary, agents, additional_info), working memories (messages, structured_data, binary_data, tags, metadata), and long-term memories (memory, tags, metadata).',
        'input_schema': UpdateAgenticMemoryArgs.model_json_schema(),
        'function': update_agentic_memory_tool,
        'args_model': UpdateAgenticMemoryArgs,
        'min_version': '3.3.0',
        'http_methods': 'PUT',
    },
    'DeleteAgenticMemoryByIDTool': {
        'display_name': 'DeleteAgenticMemoryByIDTool',
        'description': 'Deletes a specific agentic memory by its type and ID from a memory container.',
        'input_schema': DeleteAgenticMemoryByIDArgs.model_json_schema(),
        'function': delete_agentic_memory_by_id_tool,
        'args_model': DeleteAgenticMemoryByIDArgs,
        'min_version': '3.3.0',
        'http_methods': 'DELETE',
    },
    'DeleteAgenticMemoryByQueryTool': {
        'display_name': 'DeleteAgenticMemoryByQueryTool',
        'description': 'Deletes agentic memories matching a query from a memory container. Uses OpenSearch query DSL to match memories for deletion.',
        'input_schema': DeleteAgenticMemoryByQueryArgs.model_json_schema(),
        'function': delete_agentic_memory_by_query_tool,
        'args_model': DeleteAgenticMemoryByQueryArgs,
        'min_version': '3.3.0',
        'http_methods': 'POST',
    },
    'SearchAgenticMemoryTool': {
        'display_name': 'SearchAgenticMemoryTool',
        'description': 'Searches memories of a specific type within an agentic memory container using OpenSearch query DSL. Supports sorting of results.',
        'input_schema': SearchAgenticMemoryArgs.model_json_schema(),
        'function': search_agentic_memory_tool,
        'args_model': SearchAgenticMemoryArgs,
        'min_version': '3.3.0',
        'http_methods': 'GET',
    },
}

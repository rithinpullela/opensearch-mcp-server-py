# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
from .agentic_memory.actions import AGENTIC_MEMORY_TOOLS_REGISTRY
from .compat import check_tool_compatibility as _check_tool_compatibility
from .memory_tools import MEMORY_TOOLS_REGISTRY
from .skills_tools import SKILLS_TOOLS_REGISTRY
from .tool_logging import log_tool_error
from .tool_params import (
    CatNodesArgs,
    CreateExperimentArgs,
    CreateJudgmentListArgs,
    CreateLLMJudgmentListArgs,
    CreateQuerySetArgs,
    CreateSearchConfigurationArgs,
    CreateUBIJudgmentListArgs,
    DeleteExperimentArgs,
    DeleteJudgmentListArgs,
    DeleteQuerySetArgs,
    DeleteSearchConfigurationArgs,
    GetAllocationArgs,
    GetClusterStateArgs,
    GetExperimentArgs,
    GetIndexInfoArgs,
    GetIndexMappingArgs,
    GetIndexStatsArgs,
    GetJudgmentListArgs,
    GetLongRunningTasksArgs,
    GetNodesArgs,
    GetNodesHotThreadsArgs,
    GetQueryInsightsArgs,
    GetQuerySetArgs,
    GetSearchConfigurationArgs,
    GetSegmentsArgs,
    GetShardsArgs,
    ListClustersArgs,
    ListIndicesArgs,
    SampleQuerySetArgs,
    SearchExperimentsArgs,
    SearchIndexArgs,
    SearchJudgmentsArgs,
    SearchQuerySetsArgs,
    SearchSearchConfigurationsArgs,
    baseToolArgs,
)
from .utils import format_json
from mcp_server_opensearch.clusters_information import cluster_registry
from opensearch.helper import (
    convert_search_results_to_csv,
    create_experiment,
    create_judgment_list,
    create_llm_judgment_list,
    create_query_set,
    create_search_configuration,
    create_ubi_judgment_list,
    delete_experiment,
    delete_judgment_list,
    delete_query_set,
    delete_search_configuration,
    get_allocation,
    get_cluster_state,
    get_experiment,
    get_index,
    get_index_info,
    get_index_mapping,
    get_index_stats,
    get_judgment_list,
    get_long_running_tasks,
    get_nodes,
    get_nodes_hot_threads,
    get_nodes_info,
    get_opensearch_version,
    get_query_insights,
    get_query_set,
    get_search_configuration,
    get_segments,
    get_shards,
    list_indices,
    sample_query_set,
    search_experiments,
    search_index,
    search_judgments,
    search_query_sets,
    search_search_configurations,
)


async def list_clusters_tool(args: ListClustersArgs) -> list[dict]:
    """List all available OpenSearch clusters."""
    try:
        cluster_names = list(cluster_registry.keys())
        formatted_names = json.dumps(cluster_names, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Available clusters:\n{formatted_names}'}]
    except Exception as e:
        return log_tool_error('ListClustersTool', e, 'listing clusters')


async def check_tool_compatibility(tool_name: str, args: baseToolArgs = None):
    """Check if a tool is compatible with the current OpenSearch version.

    Delegates to the cycle-free leaf module ``tools.compat``; the registry and the
    version fetcher are injected so that module never imports the client/registry
    directly. Behavior (message text, bare ``Exception`` on mismatch) is identical.
    """
    await _check_tool_compatibility(
        tool_name,
        registry=TOOL_REGISTRY,
        version_fetcher=get_opensearch_version,
        args=args,
    )


async def list_indices_tool(args: ListIndicesArgs) -> list[dict]:
    """List indices with optional detailed information."""
    try:
        await check_tool_compatibility('ListIndexTool', args)

        if args.include_detail:
            # Return detailed information
            if args.index:
                # Return detailed information for specific index or pattern
                index_info = await get_index(args)
                formatted_info = format_json(index_info)
                return [
                    {
                        'type': 'text',
                        'text': f'Index information for {args.index}:\n{formatted_info}',
                    }
                ]
            else:
                # Return full metadata for all indices
                indices = await list_indices(args)
                formatted_indices = format_json(indices)
                return [{'type': 'text', 'text': f'All indices information:\n{formatted_indices}'}]
        else:
            # Return minimal information (names only)
            indices = await list_indices(args)
            index_names = [
                item.get('index') for item in indices if isinstance(item, dict) and 'index' in item
            ]
            formatted_names = format_json(index_names)
            return [{'type': 'text', 'text': f'Indices:\n{formatted_names}'}]
    except Exception as e:
        return log_tool_error(
            'ListIndexTool', e, 'listing indices', index=getattr(args, 'index', None)
        )


async def get_index_mapping_tool(args: GetIndexMappingArgs) -> list[dict]:
    """Get the mapping for a specific index."""
    try:
        await check_tool_compatibility('IndexMappingTool', args)
        mapping = await get_index_mapping(args)
        formatted_mapping = format_json(mapping)

        return [{'type': 'text', 'text': f'Mapping for {args.index}:\n{formatted_mapping}'}]
    except Exception as e:
        return log_tool_error('IndexMappingTool', e, 'getting mapping', index=args.index)


async def search_index_tool(args: SearchIndexArgs) -> list[dict]:
    """Search an index using query DSL."""
    try:
        await check_tool_compatibility('SearchIndexTool', args)
        result = await search_index(args)

        if args.format.lower() == 'csv':
            csv_result = convert_search_results_to_csv(result)
            return [
                {
                    'type': 'text',
                    'text': f'Search results from {args.index} (CSV format):\n{csv_result}',
                }
            ]
        else:
            formatted_result = format_json(result)
            return [
                {
                    'type': 'text',
                    'text': f'Search results from {args.index} (JSON format):\n{formatted_result}',
                }
            ]
    except Exception as e:
        return log_tool_error('SearchIndexTool', e, 'searching index', index=args.index)


async def get_shards_tool(args: GetShardsArgs) -> list[dict]:
    """Get shard information for an index."""
    try:
        await check_tool_compatibility('GetShardsTool', args)
        result = await get_shards(args)

        if isinstance(result, dict) and 'error' in result:
            return log_tool_error(
                'GetShardsTool',
                Exception(result['error']),
                'getting shards',
                index=getattr(args, 'index', None),
            )
        formatted_text = 'index | shard | prirep | state | docs | store | ip | node\n'

        # Format each shard row
        for shard in result:
            formatted_text += f'{shard["index"]} | '
            formatted_text += f'{shard["shard"]} | '
            formatted_text += f'{shard["prirep"]} | '
            formatted_text += f'{shard["state"]} | '
            formatted_text += f'{shard["docs"]} | '
            formatted_text += f'{shard["store"]} | '
            formatted_text += f'{shard["ip"]} | '
            formatted_text += f'{shard["node"]}\n'

        return [{'type': 'text', 'text': formatted_text}]
    except Exception as e:
        return log_tool_error(
            'GetShardsTool', e, 'getting shards information', index=getattr(args, 'index', None)
        )


async def get_cluster_state_tool(args: GetClusterStateArgs) -> list[dict]:
    """Tool to get the current state of the cluster.

    Args:
        args: GetClusterStateArgs containing optional metric and index filters

    Returns:
        list[dict]: Cluster state information in MCP format
    """
    try:
        await check_tool_compatibility('GetClusterStateTool', args)
        result = await get_cluster_state(args)

        # Format the response for better readability
        formatted_result = format_json(result)

        # Create response message based on what was requested
        message = 'Cluster state information'
        if args.metric:
            message += f' for metric: {args.metric}'
        if args.index:
            message += f', filtered by index: {args.index}'

        return [{'type': 'text', 'text': f'{message}:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('GetClusterStateTool', e, 'getting cluster state')


async def get_segments_tool(args: GetSegmentsArgs) -> list[dict]:
    """Tool to get information about Lucene segments in indices.

    Args:
        args: GetSegmentsArgs containing optional index filter

    Returns:
        list[dict]: Segment information in MCP format
    """
    try:
        await check_tool_compatibility('GetSegmentsTool', args)
        result = await get_segments(args)

        if isinstance(result, dict) and 'error' in result:
            return log_tool_error(
                'GetSegmentsTool',
                Exception(result['error']),
                'getting segments',
                index=getattr(args, 'index', None),
            )

        # Create a formatted table for better readability
        formatted_text = 'index | shard | prirep | segment | generation | docs.count | docs.deleted | size | memory.bookkeeping | memory.vectors | memory.docvalues | memory.terms | version\n'

        # Format each segment row
        for segment in result:
            formatted_text += f'{segment.get("index", "N/A")} | '
            formatted_text += f'{segment.get("shard", "N/A")} | '
            formatted_text += f'{segment.get("prirep", "N/A")} | '
            formatted_text += f'{segment.get("segment", "N/A")} | '
            formatted_text += f'{segment.get("generation", "N/A")} | '
            formatted_text += f'{segment.get("docs.count", "N/A")} | '
            formatted_text += f'{segment.get("docs.deleted", "N/A")} | '
            formatted_text += f'{segment.get("size", "N/A")} | '
            formatted_text += f'{segment.get("memory.bookkeeping", "N/A")} | '
            formatted_text += f'{segment.get("memory.vectors", "N/A")} | '
            formatted_text += f'{segment.get("memory.docvalues", "N/A")} | '
            formatted_text += f'{segment.get("memory.terms", "N/A")} | '
            formatted_text += f'{segment.get("version", "N/A")}\n'

        # Create response message based on what was requested
        message = 'Segment information'
        if args.index:
            message += f' for index: {args.index}'
        else:
            message += ' for all indices'

        return [{'type': 'text', 'text': f'{message}:\n{formatted_text}'}]
    except Exception as e:
        return log_tool_error(
            'GetSegmentsTool', e, 'getting segment information', index=getattr(args, 'index', None)
        )


async def cat_nodes_tool(args: CatNodesArgs) -> list[dict]:
    """Tool to get information about nodes in the cluster.

    Args:
        args: CatNodesArgs containing optional metrics filter

    Returns:
        list[dict]: Node information in MCP format
    """
    try:
        await check_tool_compatibility('CatNodesTool', args)
        result = await get_nodes(args)

        if isinstance(result, dict) and 'error' in result:
            return log_tool_error(
                'CatNodesTool', Exception(result['error']), 'getting node information'
            )

        # If no nodes found
        if not result:
            return [{'type': 'text', 'text': 'No nodes found in the cluster.'}]

        # Get all available columns from the first node
        columns = list(result[0].keys())

        # Create a formatted table header
        formatted_text = ' | '.join(columns) + '\n'

        # Format each node row
        for node in result:
            row_values = []
            for col in columns:
                row_values.append(str(node.get(col, 'N/A')))
            formatted_text += ' | '.join(row_values) + '\n'

        # Create response message based on what was requested
        message = 'Node information for the cluster'
        if args.metrics:
            message += f' (metrics: {args.metrics})'

        return [{'type': 'text', 'text': f'{message}:\n{formatted_text}'}]
    except Exception as e:
        return log_tool_error('CatNodesTool', e, 'getting node information')


async def get_index_info_tool(args: GetIndexInfoArgs) -> list[dict]:
    """Tool to get detailed information about an index including mappings, settings, and aliases.

    Args:
        args: GetIndexInfoArgs containing the index name

    Returns:
        list[dict]: Index information in MCP format
    """
    try:
        await check_tool_compatibility('GetIndexInfoTool', args)
        result = await get_index_info(args)

        # Format the response for better readability
        formatted_result = format_json(result)

        # Create response message
        message = f'Detailed information for index: {args.index}'

        return [{'type': 'text', 'text': f'{message}:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('GetIndexInfoTool', e, 'getting index information', index=args.index)


async def get_index_stats_tool(args: GetIndexStatsArgs) -> list[dict]:
    """Tool to get statistics about an index.

    Args:
        args: GetIndexStatsArgs containing the index name and optional metric filter

    Returns:
        list[dict]: Index statistics in MCP format
    """
    try:
        await check_tool_compatibility('GetIndexStatsTool', args)
        result = await get_index_stats(args)

        # Format the response for better readability
        formatted_result = format_json(result)

        # Create response message based on what was requested
        message = f'Statistics for index: {args.index}'
        if args.metric:
            message += f' (metrics: {args.metric})'

        return [{'type': 'text', 'text': f'{message}:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('GetIndexStatsTool', e, 'getting index statistics', index=args.index)


async def get_query_insights_tool(args: GetQueryInsightsArgs) -> list[dict]:
    """Tool to get query insights from the /_insights/top_queries endpoint.

    Args:
        args: GetQueryInsightsArgs containing connection parameters

    Returns:
        list[dict]: Query insights in MCP format
    """
    try:
        await check_tool_compatibility('GetQueryInsightsTool', args)
        result = await get_query_insights(args)

        # Format the response for better readability
        formatted_result = format_json(result)

        # Create simple response message
        message = 'Query insights from /_insights/top_queries endpoint'

        return [{'type': 'text', 'text': f'{message}:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('GetQueryInsightsTool', e, 'getting query insights')


async def get_nodes_hot_threads_tool(args: GetNodesHotThreadsArgs) -> list[dict]:
    """Tool to get information about hot threads in the cluster nodes.

    Args:
        args: GetNodesHotThreadsArgs containing connection parameters

    Returns:
        list[dict]: Hot threads information in MCP format
    """
    try:
        await check_tool_compatibility('GetNodesHotThreadsTool', args)
        result = await get_nodes_hot_threads(args)

        # Create simple response message
        message = 'Hot threads information from /_nodes/hot_threads endpoint'

        # The hot_threads API returns text, not JSON, so we don't need to format it
        return [{'type': 'text', 'text': f'{message}:\n{result}'}]
    except Exception as e:
        return log_tool_error('GetNodesHotThreadsTool', e, 'getting hot threads information')


async def get_allocation_tool(args: GetAllocationArgs) -> list[dict]:
    """Tool to get information about shard allocation across nodes in the cluster.

    Args:
        args: GetAllocationArgs containing connection parameters

    Returns:
        list[dict]: Allocation information in MCP format
    """
    try:
        await check_tool_compatibility('GetAllocationTool', args)
        result = await get_allocation(args)

        if isinstance(result, dict) and 'error' in result:
            return log_tool_error(
                'GetAllocationTool', Exception(result['error']), 'getting allocation information'
            )

        # If no allocation information found
        if not result:
            return [{'type': 'text', 'text': 'No allocation information found in the cluster.'}]

        # Get all available columns from the first allocation entry
        columns = list(result[0].keys())

        # Create a formatted table header
        formatted_text = ' | '.join(columns) + '\n'

        # Format each allocation row
        for allocation in result:
            row_values = []
            for col in columns:
                row_values.append(str(allocation.get(col, 'N/A')))
            formatted_text += ' | '.join(row_values) + '\n'

        # Create simple response message
        message = 'Allocation information from /_cat/allocation endpoint'

        return [{'type': 'text', 'text': f'{message}:\n{formatted_text}'}]
    except Exception as e:
        return log_tool_error('GetAllocationTool', e, 'getting allocation information')


async def get_nodes_tool(args: GetNodesArgs) -> list[dict]:
    """Tool to get detailed information about nodes in the cluster.

    Args:
        args: GetNodesArgs containing optional node_id, metric filters, and other parameters

    Returns:
        list[dict]: Detailed node information in MCP format
    """
    try:
        await check_tool_compatibility('GetNodesTool', args)
        result = await get_nodes_info(args)

        if isinstance(result, dict) and 'error' in result:
            return log_tool_error(
                'GetNodesTool', Exception(result['error']), 'getting nodes information'
            )

        # Format the response for better readability
        formatted_result = format_json(result)

        # Create response message based on what was requested
        message = 'Detailed node information'
        if args.node_id:
            message += f' for nodes: {args.node_id}'
        else:
            message += ' for all nodes'

        if args.metric:
            message += f' (metrics: {args.metric})'

        return [{'type': 'text', 'text': f'{message}:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('GetNodesTool', e, 'getting nodes information')


async def get_long_running_tasks_tool(args: GetLongRunningTasksArgs) -> list[dict]:
    """Tool to get information about long-running tasks in the cluster, sorted by running time.

    Args:
        args: GetLongRunningTasksArgs containing limit parameter

    Returns:
        list[dict]: Long-running tasks information in MCP format
    """
    try:
        await check_tool_compatibility('GetLongRunningTasksTool', args)
        result = await get_long_running_tasks(args)

        if isinstance(result, dict) and 'error' in result:
            return log_tool_error(
                'GetLongRunningTasksTool', Exception(result['error']), 'getting long-running tasks'
            )

        # If no tasks found
        if not result:
            return [{'type': 'text', 'text': 'No tasks found in the cluster.'}]

        # Get all available columns from the first task entry
        columns = list(result[0].keys())

        # Create a formatted table header
        formatted_text = ' | '.join(columns) + '\n'

        # Format each task row
        for task in result:
            row_values = []
            for col in columns:
                row_values.append(str(task.get(col, 'N/A')))
            formatted_text += ' | '.join(row_values) + '\n'

        # Create response message based on what was requested
        message = f'Top {len(result)} long-running tasks sorted by running time'

        return [{'type': 'text', 'text': f'{message}:\n{formatted_text}'}]
    except Exception as e:
        return log_tool_error(
            'GetLongRunningTasksTool', e, 'getting long-running tasks information'
        )


async def create_search_configuration_tool(args: CreateSearchConfigurationArgs) -> list[dict]:
    """Tool to create a search configuration via the Search Relevance plugin.

    Args:
        args: CreateSearchConfigurationArgs

    Returns:
        list[dict]: Created configuration details in MCP format
    """
    try:
        await check_tool_compatibility('CreateSearchConfigurationTool', args)
        result = await create_search_configuration(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'Search configuration created:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('CreateSearchConfigurationTool', e, 'creating search configuration')


async def get_search_configuration_tool(args: GetSearchConfigurationArgs) -> list[dict]:
    """Tool to retrieve a search configuration by ID.

    Args:
        args: GetSearchConfigurationArgs

    Returns:
        list[dict]: Search configuration details in MCP format
    """
    try:
        await check_tool_compatibility('GetSearchConfigurationTool', args)
        result = await get_search_configuration(args)
        formatted_result = format_json(result)
        return [
            {
                'type': 'text',
                'text': f'Search configuration {args.search_configuration_id}:\n{formatted_result}',
            }
        ]
    except Exception as e:
        return log_tool_error('GetSearchConfigurationTool', e, 'retrieving search configuration')


async def delete_search_configuration_tool(args: DeleteSearchConfigurationArgs) -> list[dict]:
    """Tool to delete a search configuration by ID.

    Args:
        args: DeleteSearchConfigurationArgs

    Returns:
        list[dict]: Deletion result in MCP format
    """
    try:
        await check_tool_compatibility('DeleteSearchConfigurationTool', args)
        result = await delete_search_configuration(args)
        formatted_result = format_json(result)
        return [
            {
                'type': 'text',
                'text': f'Search configuration {args.search_configuration_id} deleted:\n{formatted_result}',
            }
        ]
    except Exception as e:
        return log_tool_error('DeleteSearchConfigurationTool', e, 'deleting search configuration')


async def get_query_set_tool(args: GetQuerySetArgs) -> list[dict]:
    """Tool to retrieve a specific query set by ID from the Search Relevance plugin.

    Args:
        args: GetQuerySetArgs containing the query_set_id

    Returns:
        list[dict]: Query set details in MCP format
    """
    try:
        await check_tool_compatibility('GetQuerySetTool', args)
        result = await get_query_set(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'Query set {args.query_set_id}:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('GetQuerySetTool', e, 'retrieving query set')


async def create_query_set_tool(args: CreateQuerySetArgs) -> list[dict]:
    """Tool to create a new query set with a list of queries.

    Args:
        args: CreateQuerySetArgs containing name, queries (JSON string), and optional description

    Returns:
        list[dict]: Result of the creation operation in MCP format
    """
    try:
        await check_tool_compatibility('CreateQuerySetTool', args)
        result = await create_query_set(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'Query set created:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('CreateQuerySetTool', e, 'creating query set')


async def sample_query_set_tool(args: SampleQuerySetArgs) -> list[dict]:
    """Tool to create a query set by sampling top queries from user behavior data (UBI).

    Args:
        args: SampleQuerySetArgs containing name, query_set_size, and optional description

    Returns:
        list[dict]: Result of the sampling operation in MCP format
    """
    try:
        await check_tool_compatibility('SampleQuerySetTool', args)
        result = await sample_query_set(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'Query set sampled:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('SampleQuerySetTool', e, 'sampling query set')


async def delete_query_set_tool(args: DeleteQuerySetArgs) -> list[dict]:
    """Tool to delete a query set by ID.

    Args:
        args: DeleteQuerySetArgs containing the query_set_id

    Returns:
        list[dict]: Result of the deletion operation in MCP format
    """
    try:
        await check_tool_compatibility('DeleteQuerySetTool', args)
        result = await delete_query_set(args)
        formatted_result = format_json(result)
        return [
            {'type': 'text', 'text': f'Query set {args.query_set_id} deleted:\n{formatted_result}'}
        ]
    except Exception as e:
        return log_tool_error('DeleteQuerySetTool', e, 'deleting query set')


async def get_judgment_list_tool(args: GetJudgmentListArgs) -> list[dict]:
    """Tool to retrieve a specific judgment list by ID from the Search Relevance plugin.

    Args:
        args: GetJudgmentListArgs containing the judgment_id

    Returns:
        list[dict]: Judgment list details in MCP format
    """
    try:
        await check_tool_compatibility('GetJudgmentListTool', args)
        result = await get_judgment_list(args)
        formatted_result = format_json(result)
        return [
            {'type': 'text', 'text': f'Judgment list: {args.judgment_id}:\n{formatted_result}'}
        ]
    except Exception as e:
        return log_tool_error('GetJudgmentListTool', e, 'retrieving judgment list')


async def create_judgment_list_tool(args: CreateJudgmentListArgs) -> list[dict]:
    """Tool to create a judgment list with manual relevance ratings.

    Args:
        args: CreateJudgmentListArgs containing name, judgment_ratings (JSON string), and optional description

    Returns:
        list[dict]: Result of the creation operation in MCP format
    """
    try:
        await check_tool_compatibility('CreateJudgmentListTool', args)
        result = await create_judgment_list(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'Judgment created:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('CreateJudgmentListTool', e, 'creating judgment list')


async def create_ubi_judgment_list_tool(args: CreateUBIJudgmentListArgs) -> list[dict]:
    """Tool to create a judgment list by mining relevance signals from UBI click data.

    Args:
        args: CreateUBIJudgmentListArgs containing name, click_model, max_rank, and optional date range

    Returns:
        list[dict]: Result of the creation operation in MCP format
    """
    try:
        await check_tool_compatibility('CreateUBIJudgmentListTool', args)
        result = await create_ubi_judgment_list(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'UBI judgment created:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('CreateUBIJudgmentListTool', e, 'creating UBI judgment')


async def delete_judgment_list_tool(args: DeleteJudgmentListArgs) -> list[dict]:
    """Tool to delete a judgment list by ID from the Search Relevance plugin.

    Args:
        args: DeleteJudgmentListArgs containing the judgment_id

    Returns:
        list[dict]: Result of the deletion operation in MCP format
    """
    try:
        await check_tool_compatibility('DeleteJudgmentListTool', args)
        result = await delete_judgment_list(args)
        formatted_result = format_json(result)
        return [
            {
                'type': 'text',
                'text': f'Judgment list {args.judgment_id} deleted:\n{formatted_result}',
            }
        ]
    except Exception as e:
        return log_tool_error('DeleteJudgmentListTool', e, 'deleting judgment list')


async def create_llm_judgment_list_tool(args: CreateLLMJudgmentListArgs) -> list[dict]:
    """Tool to create a judgment list using an LLM model via the Search Relevance plugin.

    For each query in the query set, the top k documents are retrieved using the
    specified search configuration and rated by the LLM model.

    Args:
        args: CreateLLMJudgmentListArgs containing name, query_set_id, search_configuration_id,
              model_id, size, and optional context_fields

    Returns:
        list[dict]: Result of the creation operation in MCP format
    """
    try:
        await check_tool_compatibility('CreateLLMJudgmentListTool', args)
        result = await create_llm_judgment_list(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'LLM judgment list created:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('CreateLLMJudgmentListTool', e, 'creating LLM judgment list')


async def get_experiment_tool(args: GetExperimentArgs) -> list[dict]:
    """Tool to retrieve a specific experiment by ID from the Search Relevance plugin.

    Args:
        args: GetExperimentArgs containing the experiment_id

    Returns:
        list[dict]: Experiment details in MCP format
    """
    try:
        await check_tool_compatibility('GetExperimentTool', args)
        result = await get_experiment(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'Experiment {args.experiment_id}:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('GetExperimentTool', e, 'retrieving experiment')


async def create_experiment_tool(args: CreateExperimentArgs) -> list[dict]:
    """Tool to create a search relevance experiment via the Search Relevance plugin.

    Args:
        args: CreateExperimentArgs containing query_set_id, search_configuration_ids,
              experiment_type, size, and optional judgment_list_ids

    Returns:
        list[dict]: Result of the creation operation in MCP format
    """
    try:
        await check_tool_compatibility('CreateExperimentTool', args)
        result = await create_experiment(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'Experiment created:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('CreateExperimentTool', e, 'creating experiment')


async def delete_experiment_tool(args: DeleteExperimentArgs) -> list[dict]:
    """Tool to delete an experiment by ID from the Search Relevance plugin.

    Args:
        args: DeleteExperimentArgs containing the experiment_id

    Returns:
        list[dict]: Result of the deletion operation in MCP format
    """
    try:
        await check_tool_compatibility('DeleteExperimentTool', args)
        result = await delete_experiment(args)
        formatted_result = format_json(result)
        return [
            {
                'type': 'text',
                'text': f'Experiment {args.experiment_id} deleted:\n{formatted_result}',
            }
        ]
    except Exception as e:
        return log_tool_error('DeleteExperimentTool', e, 'deleting experiment')


async def search_query_sets_tool(args: SearchQuerySetsArgs) -> list[dict]:
    """Tool to search query sets using OpenSearch query DSL.

    Args:
        args: SearchQuerySetsArgs containing an optional query_body

    Returns:
        list[dict]: Search results in MCP format
    """
    try:
        await check_tool_compatibility('SearchQuerySetsTool', args)
        result = await search_query_sets(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'Query set search results:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('SearchQuerySetsTool', e, 'searching query sets')


async def search_search_configurations_tool(args: SearchSearchConfigurationsArgs) -> list[dict]:
    """Tool to search search configurations using OpenSearch query DSL.

    Args:
        args: SearchSearchConfigurationsArgs containing an optional query_body

    Returns:
        list[dict]: Search results in MCP format
    """
    try:
        await check_tool_compatibility('SearchSearchConfigurationsTool', args)
        result = await search_search_configurations(args)
        formatted_result = format_json(result)
        return [
            {'type': 'text', 'text': f'Search configuration search results:\n{formatted_result}'}
        ]
    except Exception as e:
        return log_tool_error(
            'SearchSearchConfigurationsTool', e, 'searching search configurations'
        )


async def search_judgments_tool(args: SearchJudgmentsArgs) -> list[dict]:
    """Tool to search judgments using OpenSearch query DSL.

    Args:
        args: SearchJudgmentsArgs containing an optional query_body

    Returns:
        list[dict]: Search results in MCP format
    """
    try:
        await check_tool_compatibility('SearchJudgmentsTool', args)
        result = await search_judgments(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'Judgment search results:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('SearchJudgmentsTool', e, 'searching judgments')


async def search_experiments_tool(args: SearchExperimentsArgs) -> list[dict]:
    """Tool to search experiments using OpenSearch query DSL.

    Args:
        args: SearchExperimentsArgs containing an optional query_body

    Returns:
        list[dict]: Search results in MCP format
    """
    try:
        await check_tool_compatibility('SearchExperimentsTool', args)
        result = await search_experiments(args)
        formatted_result = format_json(result)
        return [{'type': 'text', 'text': f'Experiment search results:\n{formatted_result}'}]
    except Exception as e:
        return log_tool_error('SearchExperimentsTool', e, 'searching experiments')


# Registry of available OpenSearch tools with their metadata.
#
# Assembled at import time from per-domain sources (skills / agentic-memory / memory
# sub-registries + the inline `core` block in tools/domains/core.py + the 4 static
# ex-generated tools), composed in the canonical group order by
# `tools.modules.compose_registry`. This replaced a 343-line inline dict literal; the
# handler functions remain in this module and are imported by the domain module(s).
#
# IMPORTANT: TOOL_REGISTRY must stay a PLAIN dict — `config.apply_custom_tool_config`
# calls `.update()` on it and `tool_filter` calls `.pop()`; `ToolRegistry` would
# reject re-adds / lack `.pop`. `compose_registry(...).as_dict()` returns a plain dict
# (with fail-loud duplicate detection applied during composition). The composed order
# (and the 4-tool generated tail) is pinned by tests/tools/test_modules.py.
#
# Imports are at the BOTTOM (after all handler defs) to avoid an import cycle:
# domains/core.py imports the handler functions from this module.
from .domains.core import CORE_TOOLS  # noqa: E402
from .domains.generated.register import build_generated_tools  # noqa: E402
from .modules import compose_registry  # noqa: E402


def _build_tool_registry() -> dict:
    """Compose the full tool catalog as a plain dict, in canonical group order.

    Group order (legacy): skills -> agentic_memory -> memory -> core -> generated.
    The 4 ex-generated tools are folded into the `core` group's tail so they keep
    their exact legacy position (after ListClustersTool). ``version_check`` is
    injected into the generated tools' handlers exactly as before.
    """
    generated = build_generated_tools(version_check=check_tool_compatibility)
    core = {**CORE_TOOLS, **generated}
    return compose_registry(
        skills=SKILLS_TOOLS_REGISTRY,
        agentic_memory=AGENTIC_MEMORY_TOOLS_REGISTRY,
        memory=MEMORY_TOOLS_REGISTRY,
        core=core,
    ).as_dict()


TOOL_REGISTRY = _build_tool_registry()

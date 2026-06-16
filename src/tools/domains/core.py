# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Core tool catalog: the inline (non-generated, non-sub-registry) tool specs.

This holds the metadata entries for the ~35 built-in tools that used to live in the
343-line ``TOOL_REGISTRY`` dict literal in ``tools.py`` — the index/cat/node tools,
the Search Relevance plugin tools, the generic API tool, and ``ListClustersTool`` —
in their **exact legacy declaration order**. Splitting this out of the monolith is
the audit's P1 maintainability fix: each tool's spec now lives in a focused,
greppable module instead of a giant literal.

Design constraints (verified, load-bearing):
- **Handlers stay in ``tools.py``** — this is metadata relocation, not a handler
  rewrite (no git-blame reset, minimal review surface).
- To keep this module **independently importable** (no ``tools.py`` ↔ ``core.py``
  import cycle), the handler functions and arg models are imported *lazily inside*
  :func:`build_core_tools`, not at module top level. ``tools.py`` calls
  ``build_core_tools()`` at its bottom (after the handlers are defined). This mirrors
  the cycle-free pattern in ``domains/generated`` (lazy import inside the builder).
- The returned spec ``dict`` objects are built once and cached, so repeated calls
  return the same objects; the composed registry is identical key-for-key and
  value-for-value to the old catalog (pinned by ``tests/tools/test_modules.py``).
"""

from typing import Any


# Cache so build_core_tools() returns the SAME spec objects on every call (the
# value-identity the registry composition + tests rely on).
_CORE_TOOLS_CACHE: dict[str, dict] | None = None


def build_core_tools() -> dict[str, Any]:
    """Build the inline core tool specs in EXACT legacy declaration order.

    Handlers and arg models are imported here (lazily) rather than at module top
    level so this module has no import cycle with ``tools.py``. The result is cached.

    Returns:
        dict[str, dict]: canonical-name -> ToolSpec, in legacy order. Do not reorder
        — the advertised tools/list order is pinned by ``tests/tools/test_modules.py``.
    """
    global _CORE_TOOLS_CACHE
    if _CORE_TOOLS_CACHE is not None:
        return _CORE_TOOLS_CACHE

    from ..generic_api_tool import GenericOpenSearchApiArgs, generic_opensearch_api_tool
    from ..tool_params import (
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
    )
    from ..tools import (
        cat_nodes_tool,
        create_experiment_tool,
        create_judgment_list_tool,
        create_llm_judgment_list_tool,
        create_query_set_tool,
        create_search_configuration_tool,
        create_ubi_judgment_list_tool,
        delete_experiment_tool,
        delete_judgment_list_tool,
        delete_query_set_tool,
        delete_search_configuration_tool,
        get_allocation_tool,
        get_cluster_state_tool,
        get_experiment_tool,
        get_index_info_tool,
        get_index_mapping_tool,
        get_index_stats_tool,
        get_judgment_list_tool,
        get_long_running_tasks_tool,
        get_nodes_hot_threads_tool,
        get_nodes_tool,
        get_query_insights_tool,
        get_query_set_tool,
        get_search_configuration_tool,
        get_segments_tool,
        get_shards_tool,
        list_clusters_tool,
        list_indices_tool,
        sample_query_set_tool,
        search_experiments_tool,
        search_index_tool,
        search_judgments_tool,
        search_query_sets_tool,
        search_search_configurations_tool,
    )

    # The inline core tools, in EXACT legacy declaration order.
    core_tools = {
        'ListIndexTool': {
            'display_name': 'ListIndexTool',
            'description': 'Lists indices in the OpenSearch cluster. If an index name or pattern is specified, return only information about the provided index or index pattern. The include_detail flag controls output: if False, returns only index name(s); if True (default), returns full metadata.',
            'input_schema': ListIndicesArgs.model_json_schema(),
            'function': list_indices_tool,
            'args_model': ListIndicesArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET',
        },
        'IndexMappingTool': {
            'display_name': 'IndexMappingTool',
            'description': 'Retrieves index mapping and setting information for an index in OpenSearch',
            'input_schema': GetIndexMappingArgs.model_json_schema(),
            'function': get_index_mapping_tool,
            'args_model': GetIndexMappingArgs,
            'http_methods': 'GET',
        },
        'SearchIndexTool': {
            'display_name': 'SearchIndexTool',
            'description': 'Searches an index using a query written in query domain-specific language (DSL) in OpenSearch. PREREQUISITE: You need to know the mappings of the index before constructing queries.',
            'input_schema': SearchIndexArgs.model_json_schema(),
            'function': search_index_tool,
            'args_model': SearchIndexArgs,
            'http_methods': 'GET, POST',
        },
        'GetShardsTool': {
            'display_name': 'GetShardsTool',
            'description': 'Gets information about shards in OpenSearch',
            'input_schema': GetShardsArgs.model_json_schema(),
            'function': get_shards_tool,
            'args_model': GetShardsArgs,
            'http_methods': 'GET',
        },
        'GetClusterStateTool': {
            'display_name': 'GetClusterStateTool',
            'description': 'Gets the current state of the cluster including node information, index settings, and more. Can be filtered by specific metrics and indices.',
            'input_schema': GetClusterStateArgs.model_json_schema(),
            'function': get_cluster_state_tool,
            'args_model': GetClusterStateArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET',
        },
        'GetSegmentsTool': {
            'display_name': 'GetSegmentsTool',
            'description': 'Gets information about Lucene segments in indices, including memory usage, document counts, and segment sizes. Can be filtered by specific indices.',
            'input_schema': GetSegmentsArgs.model_json_schema(),
            'function': get_segments_tool,
            'args_model': GetSegmentsArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET',
        },
        'CatNodesTool': {
            'display_name': 'CatNodesTool',
            'description': 'Lists node-level information, including node roles and load metrics. Gets information about nodes metrics in the OpenSearch cluster, including system metrics pid, name, cluster_manager, ip, port, version, build, jdk, along with disk, heap, ram, and file_desc. Can be filtered to specific metrics.',
            'input_schema': CatNodesArgs.model_json_schema(),
            'function': cat_nodes_tool,
            'args_model': CatNodesArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET',
        },
        'GetIndexInfoTool': {
            'display_name': 'GetIndexInfoTool',
            'description': 'Gets detailed information about an index including mappings, settings, and aliases. Supports wildcards in index names.',
            'input_schema': GetIndexInfoArgs.model_json_schema(),
            'function': get_index_info_tool,
            'args_model': GetIndexInfoArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET',
        },
        'GetIndexStatsTool': {
            'display_name': 'GetIndexStatsTool',
            'description': 'Gets statistics about an index including document count, store size, indexing and search performance metrics. Can be filtered to specific metrics.',
            'input_schema': GetIndexStatsArgs.model_json_schema(),
            'function': get_index_stats_tool,
            'args_model': GetIndexStatsArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET',
        },
        'GetQueryInsightsTool': {
            'display_name': 'GetQueryInsightsTool',
            'description': 'Gets query insights from the /_insights/top_queries endpoint, showing information about query patterns and performance.',
            'input_schema': GetQueryInsightsArgs.model_json_schema(),
            'function': get_query_insights_tool,
            'args_model': GetQueryInsightsArgs,
            'min_version': '2.12.0',  # Query insights feature requires OpenSearch 2.12+
            'http_methods': 'GET',
        },
        'GetNodesHotThreadsTool': {
            'display_name': 'GetNodesHotThreadsTool',
            'description': 'Gets information about hot threads in the cluster nodes from the /_nodes/hot_threads endpoint.',
            'input_schema': GetNodesHotThreadsArgs.model_json_schema(),
            'function': get_nodes_hot_threads_tool,
            'args_model': GetNodesHotThreadsArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET',
        },
        'GetAllocationTool': {
            'display_name': 'GetAllocationTool',
            'description': 'Gets information about shard allocation across nodes in the cluster from the /_cat/allocation endpoint.',
            'input_schema': GetAllocationArgs.model_json_schema(),
            'function': get_allocation_tool,
            'args_model': GetAllocationArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET',
        },
        'GetLongRunningTasksTool': {
            'display_name': 'GetLongRunningTasksTool',
            'description': 'Gets information about long-running tasks in the cluster, sorted by running time in descending order.',
            'input_schema': GetLongRunningTasksArgs.model_json_schema(),
            'function': get_long_running_tasks_tool,
            'args_model': GetLongRunningTasksArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET',
        },
        'GetNodesTool': {
            'display_name': 'GetNodesTool',
            'description': 'Gets detailed information about nodes in the OpenSearch cluster, including static information like host system details, JVM info, processor type, node settings, thread pools, installed plugins, and more. Can be filtered by specific nodes and metrics.',
            'input_schema': GetNodesArgs.model_json_schema(),
            'function': get_nodes_tool,
            'args_model': GetNodesArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET',
        },
        'GetQuerySetTool': {
            'display_name': 'GetQuerySetTool',
            'description': 'Retrieves a specific query set by ID from the OpenSearch Search Relevance plugin. Query sets are collections of search queries used for relevance testing and evaluation.',
            'input_schema': GetQuerySetArgs.model_json_schema(),
            'function': get_query_set_tool,
            'args_model': GetQuerySetArgs,
            'min_version': '3.1.0',
            'http_methods': 'GET',
        },
        'CreateQuerySetTool': {
            'display_name': 'CreateQuerySetTool',
            'description': 'Creates a new query set in the OpenSearch Search Relevance plugin by providing a list of queries. Query sets are used for relevance testing and evaluation.',
            'input_schema': CreateQuerySetArgs.model_json_schema(),
            'function': create_query_set_tool,
            'args_model': CreateQuerySetArgs,
            'min_version': '3.1.0',
            'http_methods': 'PUT',
        },
        'SampleQuerySetTool': {
            'display_name': 'SampleQuerySetTool',
            'description': 'Creates a query set by sampling the top N most frequent queries from user behavior data (UBI indices) in the OpenSearch Search Relevance plugin.',
            'input_schema': SampleQuerySetArgs.model_json_schema(),
            'function': sample_query_set_tool,
            'args_model': SampleQuerySetArgs,
            'min_version': '3.1.0',
            'http_methods': 'POST',
        },
        'DeleteQuerySetTool': {
            'display_name': 'DeleteQuerySetTool',
            'description': 'Deletes a query set by ID from the OpenSearch Search Relevance plugin.',
            'input_schema': DeleteQuerySetArgs.model_json_schema(),
            'function': delete_query_set_tool,
            'args_model': DeleteQuerySetArgs,
            'min_version': '3.1.0',
            'http_methods': 'DELETE',
        },
        'GetExperimentTool': {
            'display_name': 'GetExperimentTool',
            'description': 'Retrieves a search relevance experiment by ID from the OpenSearch Search Relevance plugin.',
            'input_schema': GetExperimentArgs.model_json_schema(),
            'function': get_experiment_tool,
            'args_model': GetExperimentArgs,
            'min_version': '3.1.0',
            'http_methods': 'GET',
        },
        'CreateExperimentTool': {
            'display_name': 'CreateExperimentTool',
            'description': (
                'Creates a search relevance experiment using the OpenSearch Search Relevance plugin. '
                'Supports three experiment types: '
                'PAIRWISE_COMPARISON (compares 2 search configurations head-to-head), '
                'POINTWISE_EVALUATION (evaluates 1 configuration against judgment lists), '
                'HYBRID_OPTIMIZER (optimizes 1 configuration using judgment lists).'
            ),
            'input_schema': CreateExperimentArgs.model_json_schema(),
            'function': create_experiment_tool,
            'args_model': CreateExperimentArgs,
            'min_version': '3.1.0',
            'http_methods': 'PUT',
        },
        'DeleteExperimentTool': {
            'display_name': 'DeleteExperimentTool',
            'description': 'Deletes a search relevance experiment by ID from the OpenSearch Search Relevance plugin.',
            'input_schema': DeleteExperimentArgs.model_json_schema(),
            'function': delete_experiment_tool,
            'args_model': DeleteExperimentArgs,
            'min_version': '3.1.0',
            'http_methods': 'DELETE',
        },
        'SearchQuerySetsTool': {
            'display_name': 'SearchQuerySetsTool',
            'description': (
                'Searches query sets in the OpenSearch Search Relevance plugin using OpenSearch query DSL.'
                'Accepts a full query DSL body to filter, sort, and paginate results. '
                'Returns all query sets when called without a query body.'
            ),
            'input_schema': SearchQuerySetsArgs.model_json_schema(),
            'function': search_query_sets_tool,
            'args_model': SearchQuerySetsArgs,
            'min_version': '3.5.0',
            'http_methods': 'GET, POST',
        },
        'SearchSearchConfigurationsTool': {
            'display_name': 'SearchSearchConfigurationsTool',
            'description': (
                'Searches search configurations in the OpenSearch Search Relevance plugin using OpenSearch query DSL.'
                'Accepts a full query DSL body to filter, sort, and paginate results. '
                'Returns all search configurations when called without a query body.'
            ),
            'input_schema': SearchSearchConfigurationsArgs.model_json_schema(),
            'function': search_search_configurations_tool,
            'args_model': SearchSearchConfigurationsArgs,
            'min_version': '3.5.0',
            'http_methods': 'GET, POST',
        },
        'SearchJudgmentsTool': {
            'display_name': 'SearchJudgmentsTool',
            'description': (
                'Searches judgments in the OpenSearch Search Relevance plugin using OpenSearch query DSL.'
                'Accepts a full query DSL body to filter, sort, and paginate results. '
                'Returns all judgments when called without a query body.'
            ),
            'input_schema': SearchJudgmentsArgs.model_json_schema(),
            'function': search_judgments_tool,
            'args_model': SearchJudgmentsArgs,
            'min_version': '3.5.0',
            'http_methods': 'GET, POST',
        },
        'SearchExperimentsTool': {
            'display_name': 'SearchExperimentsTool',
            'description': (
                'Searches experiments in the OpenSearch Search Relevance plugin using OpenSearch query DSL.'
                'Accepts a full query DSL body to filter, sort, and paginate results. '
                'Returns all experiments when called without a query body.'
            ),
            'input_schema': SearchExperimentsArgs.model_json_schema(),
            'function': search_experiments_tool,
            'args_model': SearchExperimentsArgs,
            'min_version': '3.5.0',
            'http_methods': 'GET, POST',
        },
        'GenericOpenSearchApiTool': {
            'display_name': 'GenericOpenSearchApiTool',
            'description': "A flexible tool for calling any OpenSearch API endpoint. Supports all HTTP methods with custom paths, query parameters, request bodies, and headers. Use this when you need to access OpenSearch APIs that don't have dedicated tools, or when you need more control over the request. Leverages your knowledge of OpenSearch API documentation to construct appropriate requests.",
            'input_schema': GenericOpenSearchApiArgs.model_json_schema(),
            'function': generic_opensearch_api_tool,
            'args_model': GenericOpenSearchApiArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET, POST, PUT, DELETE, HEAD, PATCH',
        },
        'CreateSearchConfigurationTool': {
            'display_name': 'CreateSearchConfigurationTool',
            'description': 'Creates a new search configuration in OpenSearch using the Search Relevance plugin. '
            'The query must be an OpenSearch DSL JSON string with %SearchText% as the search placeholder.',
            'input_schema': CreateSearchConfigurationArgs.model_json_schema(),
            'function': create_search_configuration_tool,
            'args_model': CreateSearchConfigurationArgs,
            'min_version': '3.1.0',
            'http_methods': 'PUT',
        },
        'GetSearchConfigurationTool': {
            'display_name': 'GetSearchConfigurationTool',
            'description': 'Retrieves a specific search configuration by ID from OpenSearch using the Search Relevance plugin.',
            'input_schema': GetSearchConfigurationArgs.model_json_schema(),
            'function': get_search_configuration_tool,
            'args_model': GetSearchConfigurationArgs,
            'min_version': '3.1.0',
            'http_methods': 'GET',
        },
        'DeleteSearchConfigurationTool': {
            'display_name': 'DeleteSearchConfigurationTool',
            'description': 'Deletes a search configuration by ID from OpenSearch using the Search Relevance plugin.',
            'input_schema': DeleteSearchConfigurationArgs.model_json_schema(),
            'function': delete_search_configuration_tool,
            'args_model': DeleteSearchConfigurationArgs,
            'min_version': '3.1.0',
            'http_methods': 'DELETE',
        },
        'GetJudgmentListTool': {
            'display_name': 'GetJudgmentListTool',
            'description': 'Retrieves a specific judgment list by ID from OpenSearch using the Search Relevance plugin.',
            'input_schema': GetJudgmentListArgs.model_json_schema(),
            'function': get_judgment_list_tool,
            'args_model': GetJudgmentListArgs,
            'min_version': '3.1.0',
            'http_methods': 'GET',
        },
        'CreateJudgmentListTool': {
            'display_name': 'CreateJudgmentListTool',
            'description': 'Creates a judgment list with manual relevance ratings in OpenSearch using the Search Relevance plugin. '
            'Accepts a JSON array of query-ratings objects with docId and numeric rating (0–3) per document.',
            'input_schema': CreateJudgmentListArgs.model_json_schema(),
            'function': create_judgment_list_tool,
            'args_model': CreateJudgmentListArgs,
            'min_version': '3.1.0',
            'http_methods': 'PUT',
        },
        'CreateUBIJudgmentListTool': {
            'display_name': 'CreateUBIJudgmentListTool',
            'description': 'Creates a judgment list by mining relevance signals from User Behavior Insights (UBI) click data '
            'stored in OpenSearch. Requires UBI indices to be populated.',
            'input_schema': CreateUBIJudgmentListArgs.model_json_schema(),
            'function': create_ubi_judgment_list_tool,
            'args_model': CreateUBIJudgmentListArgs,
            'min_version': '3.1.0',
            'http_methods': 'PUT',
        },
        'DeleteJudgmentListTool': {
            'display_name': 'DeleteJudgmentListTool',
            'description': 'Deletes a judgment list by ID from OpenSearch using the Search Relevance plugin.',
            'input_schema': DeleteJudgmentListArgs.model_json_schema(),
            'function': delete_judgment_list_tool,
            'args_model': DeleteJudgmentListArgs,
            'min_version': '3.1.0',
            'http_methods': 'DELETE',
        },
        'CreateLLMJudgmentListTool': {
            'display_name': 'CreateLLMJudgmentListTool',
            'description': 'Creates a judgment list using an LLM model configured in OpenSearch ML Commons. '
            'For each query in the specified query set, the top k documents are retrieved via the search '
            'configuration and rated by the LLM for relevance.',
            'input_schema': CreateLLMJudgmentListArgs.model_json_schema(),
            'function': create_llm_judgment_list_tool,
            'args_model': CreateLLMJudgmentListArgs,
            'min_version': '3.1.0',
            'http_methods': 'PUT',
        },
        'ListClustersTool': {
            'display_name': 'ListClustersTool',
            'description': 'Lists all available OpenSearch clusters configured in the server. Returns the cluster names that can be used with other tools.',
            'input_schema': ListClustersArgs.model_json_schema(),
            'function': list_clusters_tool,
            'args_model': ListClustersArgs,
            'http_methods': 'GET',
            'multi_only': True,
        },
    }

    _CORE_TOOLS_CACHE = core_tools
    return core_tools

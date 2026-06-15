# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Behavioral tests for the static (ex-generated) tool handlers.

Verify the load-bearing runtime behaviors the OpenAPI generator produced:
- GET-with-body endpoint selection (``select_endpoint`` ignores method),
- msearch NDJSON body conversion,
- path-parameter substitution + remaining params as query string,
- plain ``json.dumps`` response serialization (not compact ``format_json``).
"""

import json
import pytest
from contextlib import asynccontextmanager
from tools.domains.generated import handlers
from tools.domains.generated.params import (
    ClusterHealthArgs,
    CountArgs,
    ExplainArgs,
    MsearchArgs,
)
from unittest.mock import AsyncMock, patch


async def _noop_version_check(_name, _args):
    return None


@asynccontextmanager
async def _fake_client(perform_request_mock):
    client = AsyncMock()
    client.transport.perform_request = perform_request_mock
    yield client


def _patched_client(perform_request_mock):
    """Patch get_opensearch_client (imported inside the handler) to yield a fake."""
    return patch(
        'opensearch.client.get_opensearch_client',
        return_value=_fake_client(perform_request_mock),
    )


class TestProcessBody:
    def test_msearch_json_array_string_to_ndjson(self):
        body = json.dumps([{'index': 'a'}, {'query': {'match_all': {}}}])
        out = handlers.process_body(body, 'MsearchTool')
        assert out == '{"index": "a"}\n{"query": {"match_all": {}}}\n'

    def test_msearch_list_to_ndjson(self):
        out = handlers.process_body([{'index': 'a'}, {'q': 1}], 'MsearchTool')
        assert out == '{"index": "a"}\n{"q": 1}\n'

    def test_msearch_ndjson_string_gets_trailing_newline(self):
        out = handlers.process_body('{"a":1}\n{"b":2}', 'MsearchTool')
        assert out.endswith('\n')

    def test_non_msearch_json_string_parsed(self):
        out = handlers.process_body('{"query": {"match_all": {}}}', 'CountTool')
        assert out == {'query': {'match_all': {}}}

    def test_non_msearch_invalid_json_raises(self):
        with pytest.raises(ValueError):
            handlers.process_body('{not json', 'CountTool')

    def test_none_passes_through(self):
        assert handlers.process_body(None, 'CountTool') is None


class TestSelectEndpoint:
    def test_picks_index_endpoint_when_index_present(self):
        ep = handlers.select_endpoint(handlers.ENDPOINTS_MSEARCH, {'index': 'logs'})
        assert ep['path'] == '/{index}/_msearch'

    def test_picks_bare_endpoint_when_no_index(self):
        ep = handlers.select_endpoint(handlers.ENDPOINTS_MSEARCH, {})
        assert ep['path'] == '/_msearch'


class TestHandlersRequestShape:
    async def test_msearch_get_with_ndjson_body(self):
        perform = AsyncMock(return_value={'responses': []})
        handler = handlers.make_handler(
            'MsearchTool', handlers.ENDPOINTS_MSEARCH, _noop_version_check
        )
        with _patched_client(perform):
            result = await handler(
                MsearchArgs(
                    opensearch_cluster_name='', body=[{'index': 'a'}, {'query': {'match_all': {}}}]
                )
            )
        # GET-with-body (method ignored by select_endpoint -> first endpoint is GET)
        _, kwargs = perform.call_args
        assert kwargs['method'] == 'GET'
        assert kwargs['url'] == '/_msearch'
        assert kwargs['body'] == '{"index": "a"}\n{"query": {"match_all": {}}}\n'
        # plain json.dumps serialization
        assert result[0].text == json.dumps({'responses': []})

    async def test_explain_substitutes_path_params(self):
        perform = AsyncMock(return_value={'explanation': {}})
        handler = handlers.make_handler(
            'ExplainTool', handlers.ENDPOINTS_EXPLAIN, _noop_version_check
        )
        with _patched_client(perform):
            await handler(
                ExplainArgs(
                    opensearch_cluster_name='',
                    index='myidx',
                    id='42',
                    body={'query': {'match_all': {}}},
                )
            )
        _, kwargs = perform.call_args
        assert kwargs['url'] == '/myidx/_explain/42'
        # index and id consumed as path params, not left in query
        assert 'index' not in kwargs['params']
        assert 'id' not in kwargs['params']

    async def test_count_bare_endpoint_without_index(self):
        perform = AsyncMock(return_value={'count': 7})
        handler = handlers.make_handler('CountTool', handlers.ENDPOINTS_COUNT, _noop_version_check)
        with _patched_client(perform):
            result = await handler(CountArgs(opensearch_cluster_name=''))
        _, kwargs = perform.call_args
        assert kwargs['url'] == '/_count'
        assert result[0].text == json.dumps({'count': 7})

    async def test_cluster_health_string_response_passthrough(self):
        perform = AsyncMock(return_value='green')
        handler = handlers.make_handler(
            'ClusterHealthTool', handlers.ENDPOINTS_CLUSTER_HEALTH, _noop_version_check
        )
        with _patched_client(perform):
            result = await handler(ClusterHealthArgs(opensearch_cluster_name=''))
        _, kwargs = perform.call_args
        assert kwargs['url'] == '/_cluster/health'
        # string responses pass through unchanged (not json.dumps'd)
        assert result[0].text == 'green'

    async def test_version_gate_failure_returns_error(self):
        async def failing_check(_name, _args):
            raise Exception('Tool not supported')

        perform = AsyncMock()
        handler = handlers.make_handler('CountTool', handlers.ENDPOINTS_COUNT, failing_check)
        with _patched_client(perform):
            result = await handler(CountArgs(opensearch_cluster_name=''))
        # error surfaced via log_tool_error soft-dict; request never issued
        assert result[0]['is_error'] is True
        assert result[0]['text'].startswith('Error executing CountTool:')
        perform.assert_not_called()

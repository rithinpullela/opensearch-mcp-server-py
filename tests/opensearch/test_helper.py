# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import pytest
from tools.tool_params import (
    GetIndexMappingArgs,
    GetShardsArgs,
    ListIndicesArgs,
    SearchIndexArgs,
    baseToolArgs,
)
from unittest.mock import AsyncMock, patch


class TestOpenSearchHelper:
    def setup_method(self):
        """Setup that runs before each test method."""
        from opensearch.helper import (
            get_index_mapping,
            get_shards,
            list_indices,
            search_index,
        )

        # Store functions
        self.list_indices = list_indices
        self.get_index_mapping = get_index_mapping
        self.search_index = search_index
        self.get_shards = get_shards

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_list_indices(self, mock_get_client):
        """Test list_indices function."""
        # Setup mock response
        mock_response = [
            {'index': 'index1', 'health': 'green', 'status': 'open'},
            {'index': 'index2', 'health': 'yellow', 'status': 'open'},
        ]
        mock_client = AsyncMock()
        mock_client.cat.indices = AsyncMock(return_value=mock_response)

        # Setup async context manager
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        # Execute
        result = await self.list_indices(ListIndicesArgs(opensearch_cluster_name=''))

        # Assert
        assert result == mock_response
        mock_get_client.assert_called_once_with(ListIndicesArgs(opensearch_cluster_name=''))
        mock_client.cat.indices.assert_called_once_with(index=None, format='json')

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_get_index_mapping(self, mock_get_client):
        """Test get_index_mapping function."""
        # Setup mock response
        mock_response = {
            'test-index': {
                'mappings': {
                    'properties': {
                        'field1': {'type': 'text'},
                        'field2': {'type': 'keyword'},
                    }
                }
            }
        }
        mock_client = AsyncMock()
        mock_client.indices.get_mapping = AsyncMock(return_value=mock_response)

        # Setup async context manager
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        # Execute
        result = await self.get_index_mapping(
            GetIndexMappingArgs(index='test-index', opensearch_cluster_name='')
        )

        # Assert
        assert result == mock_response
        mock_get_client.assert_called_once_with(
            GetIndexMappingArgs(index='test-index', opensearch_cluster_name='')
        )
        mock_client.indices.get_mapping.assert_called_once_with(index='test-index')

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_search_index(self, mock_get_client):
        """Test search_index function."""
        # Setup mock response
        mock_response = {
            'hits': {
                'total': {'value': 1},
                'hits': [{'_index': 'test-index', '_id': '1', '_source': {'field': 'value'}}],
            }
        }
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=mock_response)

        # Setup async context manager
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        # Setup test query
        test_query = {'query': {'match_all': {}}}

        # Execute
        result = await self.search_index(
            SearchIndexArgs(index='test-index', query_dsl=test_query, opensearch_cluster_name='')
        )

        # Assert
        assert result == mock_response
        mock_get_client.assert_called_once_with(
            SearchIndexArgs(index='test-index', query_dsl=test_query, opensearch_cluster_name='')
        )
        # The search_index function adds size to the query body (default 10, max 100)
        expected_body = {'query': {'match_all': {}}, 'size': 10}
        mock_client.search.assert_called_once_with(index='test-index', body=expected_body)

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_search_index_size_zero(self, mock_get_client):
        """Test that size=0 is respected for aggregation-only queries.

        size=0 is falsy in Python, so `if args.size else 10` would incorrectly
        fall back to 10. The fix uses `if args.size is not None else 10`.
        """
        mock_response = {
            'hits': {'total': {'value': 100}, 'hits': []},
            'aggregations': {'by_status': {'buckets': [{'key': 'opened', 'doc_count': 80}]}},
        }
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=mock_response)

        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        test_query = {
            'size': 0,
            'query': {'match_all': {}},
            'aggs': {'by_status': {'terms': {'field': 'status.keyword'}}},
        }

        result = await self.search_index(
            SearchIndexArgs(
                index='test-index', query_dsl=test_query, size=0, opensearch_cluster_name=''
            )
        )

        assert result == mock_response
        # size=0 must be passed through, not replaced with the default of 10
        expected_body = {
            'size': 0,
            'query': {'match_all': {}},
            'aggs': {'by_status': {'terms': {'field': 'status.keyword'}}},
        }
        mock_client.search.assert_called_once_with(index='test-index', body=expected_body)

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    @patch.dict('os.environ', {'OPENSEARCH_QUERY_TIMEOUT': '10s'})
    async def test_search_index_with_query_timeout(self, mock_get_client):
        """Test that OPENSEARCH_QUERY_TIMEOUT is passed as cancel_after_time_interval."""
        mock_response = {
            'hits': {
                'total': {'value': 1},
                'hits': [{'_index': 'test-index', '_id': '1', '_source': {'field': 'value'}}],
            }
        }
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=mock_response)

        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        test_query = {'query': {'match_all': {}}}

        result = await self.search_index(
            SearchIndexArgs(index='test-index', query_dsl=test_query, opensearch_cluster_name='')
        )

        assert result == mock_response
        expected_body = {'query': {'match_all': {}}, 'size': 10}
        mock_client.search.assert_called_once_with(
            index='test-index', body=expected_body, cancel_after_time_interval='10s'
        )

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    @patch.dict('os.environ', {}, clear=False)
    async def test_search_index_without_query_timeout(self, mock_get_client):
        """Test that cancel_after_time_interval is omitted when OPENSEARCH_QUERY_TIMEOUT is not set."""
        mock_response = {
            'hits': {
                'total': {'value': 1},
                'hits': [{'_index': 'test-index', '_id': '1', '_source': {'field': 'value'}}],
            }
        }
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=mock_response)

        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        test_query = {'query': {'match_all': {}}}

        # Ensure env var is not set
        import os

        os.environ.pop('OPENSEARCH_QUERY_TIMEOUT', None)

        result = await self.search_index(
            SearchIndexArgs(index='test-index', query_dsl=test_query, opensearch_cluster_name='')
        )

        assert result == mock_response
        expected_body = {'query': {'match_all': {}}, 'size': 10}
        mock_client.search.assert_called_once_with(index='test-index', body=expected_body)

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_get_shards(self, mock_get_client):
        """Test get_shards function."""
        # Setup mock response
        mock_response = [
            {
                'index': 'test-index',
                'shard': '0',
                'prirep': 'p',
                'state': 'STARTED',
                'docs': '1000',
                'store': '1mb',
                'ip': '127.0.0.1',
                'node': 'node1',
            }
        ]
        mock_client = AsyncMock()
        mock_client.cat.shards = AsyncMock(return_value=mock_response)

        # Setup async context manager
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        # Execute
        result = await self.get_shards(
            GetShardsArgs(index='test-index', opensearch_cluster_name='')
        )

        # Assert
        assert result == mock_response
        mock_get_client.assert_called_once_with(
            GetShardsArgs(index='test-index', opensearch_cluster_name='')
        )
        mock_client.cat.shards.assert_called_once_with(index='test-index', format='json')

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_list_indices_error(self, mock_get_client):
        """Test list_indices error handling."""
        # Setup mock to raise exception
        mock_client = AsyncMock()
        mock_client.cat.indices = AsyncMock(side_effect=Exception('Connection error'))

        # Setup async context manager
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        # Execute and assert
        with pytest.raises(Exception) as exc_info:
            await self.list_indices(ListIndicesArgs(opensearch_cluster_name=''))
        assert str(exc_info.value) == 'Connection error'

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_get_index_mapping_error(self, mock_get_client):
        """Test get_index_mapping error handling."""
        # Setup mock to raise exception
        mock_client = AsyncMock()
        mock_client.indices.get_mapping = AsyncMock(side_effect=Exception('Index not found'))

        # Setup async context manager
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        # Execute and assert
        with pytest.raises(Exception) as exc_info:
            await self.get_index_mapping(
                GetIndexMappingArgs(index='non-existent-index', opensearch_cluster_name='')
            )
        assert str(exc_info.value) == 'Index not found'

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_search_index_error(self, mock_get_client):
        """Test search_index error handling."""
        # Setup mock to raise exception
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(side_effect=Exception('Invalid query'))

        # Setup async context manager
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        # Execute and assert
        with pytest.raises(Exception) as exc_info:
            await self.search_index(
                SearchIndexArgs(
                    index='test-index', query_dsl={'invalid': 'query'}, opensearch_cluster_name=''
                )
            )
        assert str(exc_info.value) == 'Invalid query'

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_get_shards_error(self, mock_get_client):
        """Test get_shards error handling."""
        # Setup mock to raise exception
        mock_client = AsyncMock()
        mock_client.cat.shards = AsyncMock(side_effect=Exception('Shard not found'))

        # Setup async context manager
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        # Execute and assert
        with pytest.raises(Exception) as exc_info:
            await self.get_shards(
                GetShardsArgs(index='non-existent-index', opensearch_cluster_name='')
            )
        assert str(exc_info.value) == 'Shard not found'

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_get_opensearch_version(self, mock_get_client):
        from opensearch.helper import get_opensearch_version

        # Setup mock response
        mock_response = {'version': {'number': '2.11.1'}}
        mock_client = AsyncMock()
        mock_client.info = AsyncMock(return_value=mock_response)
        mock_client.close = AsyncMock()

        # Setup async context manager
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        # Execute
        args = baseToolArgs(opensearch_cluster_name='')
        result = await get_opensearch_version(args)
        # Assert
        assert str(result) == '2.11.1'
        mock_get_client.assert_called_once_with(args)
        mock_client.info.assert_called_once_with()

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_get_opensearch_version_error(self, mock_get_client):
        from opensearch.helper import get_opensearch_version
        from tools.tool_params import baseToolArgs

        # Setup mock to raise exception
        mock_client = AsyncMock()
        mock_client.info = AsyncMock(side_effect=Exception('Failed to get version'))
        mock_client.close = AsyncMock()

        # Setup async context manager
        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        args = baseToolArgs(opensearch_cluster_name='')
        # Execute and assert
        result = await get_opensearch_version(args)
        assert result is None

    def test_convert_search_results_to_csv_hits_only(self):
        """Test convert_search_results_to_csv with hits only."""
        import importlib.util
        import os

        spec = importlib.util.spec_from_file_location(
            'helper', os.path.join(os.path.dirname(__file__), '../../src/opensearch/helper.py')
        )
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        convert_search_results_to_csv = helper.convert_search_results_to_csv

        search_results = {
            'hits': {
                'total': {'value': 2, 'relation': 'eq'},
                'hits': [
                    {
                        '_index': 'products',
                        '_id': '1',
                        '_score': 1.5,
                        '_source': {'name': 'Laptop', 'price': 999.99, 'category': 'electronics'},
                    },
                    {
                        '_index': 'products',
                        '_id': '2',
                        '_score': 1.2,
                        '_source': {'name': 'Phone', 'price': 599.99, 'category': 'electronics'},
                    },
                ],
            }
        }

        result = convert_search_results_to_csv(search_results)
        assert '_id,_index,_score,category,name,price' in result
        assert '1,products,1.5,electronics,Laptop,999.99' in result
        assert '2,products,1.2,electronics,Phone,599.99' in result

    def test_convert_search_results_to_csv_aggregations_only(self):
        """Test convert_search_results_to_csv with aggregations only."""
        import importlib.util
        import os

        spec = importlib.util.spec_from_file_location(
            'helper', os.path.join(os.path.dirname(__file__), '../../src/opensearch/helper.py')
        )
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        convert_search_results_to_csv = helper.convert_search_results_to_csv

        search_results = {
            'hits': {'total': {'value': 100}, 'hits': []},
            'aggregations': {
                'categories': {
                    'buckets': [
                        {'key': 'electronics', 'doc_count': 45},
                        {'key': 'books', 'doc_count': 30},
                        {'key': 'clothing', 'doc_count': 25},
                    ]
                },
                'avg_price': {'value': 299.99},
            },
        }

        result = convert_search_results_to_csv(search_results)
        assert 'categories' in result
        assert 'avg_price' in result
        assert 'electronics' in result
        assert '299.99' in result

    def test_convert_search_results_to_csv_hits_and_aggregations(self):
        """Test convert_search_results_to_csv with both hits and aggregations."""
        import importlib.util
        import os

        spec = importlib.util.spec_from_file_location(
            'helper', os.path.join(os.path.dirname(__file__), '../../src/opensearch/helper.py')
        )
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        convert_search_results_to_csv = helper.convert_search_results_to_csv

        search_results = {
            'hits': {
                'total': {'value': 1},
                'hits': [
                    {
                        '_index': 'products',
                        '_id': '1',
                        '_score': 1.0,
                        '_source': {'name': 'Laptop', 'price': 999.99},
                    }
                ],
            },
            'aggregations': {'price_stats': {'min': 99.99, 'max': 1999.99, 'avg': 549.99}},
        }

        result = convert_search_results_to_csv(search_results)
        assert 'SEARCH HITS:' in result
        assert 'AGGREGATIONS:' in result
        assert '_id,_index,_score,name,price' in result
        assert '1,products,1.0,Laptop,999.99' in result
        assert 'price_stats' in result
        assert '549.99' in result

    def test_convert_search_results_to_csv_nested_aggregations(self):
        """Test convert_search_results_to_csv with nested aggregations."""
        import importlib.util
        import os

        spec = importlib.util.spec_from_file_location(
            'helper', os.path.join(os.path.dirname(__file__), '../../src/opensearch/helper.py')
        )
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        convert_search_results_to_csv = helper.convert_search_results_to_csv

        search_results = {
            'hits': {'total': {'value': 1000}, 'hits': []},
            'aggregations': {
                'categories': {
                    'buckets': [
                        {
                            'key': 'electronics',
                            'doc_count': 500,
                            'avg_price': {'value': 299.99},
                            'brands': {
                                'buckets': [
                                    {'key': 'Apple', 'doc_count': 200},
                                    {'key': 'Samsung', 'doc_count': 150},
                                ]
                            },
                        },
                        {
                            'key': 'books',
                            'doc_count': 300,
                            'avg_price': {'value': 19.99},
                            'genres': {
                                'buckets': [
                                    {'key': 'fiction', 'doc_count': 180},
                                    {'key': 'non-fiction', 'doc_count': 120},
                                ]
                            },
                        },
                    ]
                },
                'total_revenue': {'value': 125000.50},
            },
        }

        result = convert_search_results_to_csv(search_results)
        assert 'categories' in result
        assert 'total_revenue' in result
        assert 'electronics' in result
        assert 'Apple' in result
        assert 'fiction' in result
        assert '125000.5' in result

    def test_convert_search_results_to_csv_nested_objects(self):
        """Test convert_search_results_to_csv with nested objects in hits."""
        import importlib.util
        import os

        spec = importlib.util.spec_from_file_location(
            'helper', os.path.join(os.path.dirname(__file__), '../../src/opensearch/helper.py')
        )
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        convert_search_results_to_csv = helper.convert_search_results_to_csv

        search_results = {
            'hits': {
                'hits': [
                    {
                        '_index': 'users',
                        '_id': '1',
                        '_score': 1.0,
                        '_source': {
                            'name': 'John Doe',
                            'address': {
                                'street': '123 Main St',
                                'city': 'New York',
                                'coordinates': {'lat': 40.7128, 'lon': -74.0060},
                            },
                            'tags': ['developer', 'python'],
                            'skills': [
                                {'name': 'Python', 'level': 'expert'},
                                {'name': 'JavaScript', 'level': 'intermediate'},
                            ],
                        },
                    }
                ]
            }
        }

        result = convert_search_results_to_csv(search_results)
        # Check flattened nested fields
        assert 'address.city' in result
        assert 'address.coordinates.lat' in result
        assert 'address.coordinates.lon' in result
        assert 'New York' in result
        assert '40.7128' in result
        assert '-74.006' in result
        # Check arrays are JSON encoded (CSV escapes quotes)
        assert '"[""developer"", ""python""]"' in result

    def test_convert_search_results_to_csv_empty_results(self):
        """Test convert_search_results_to_csv with empty results."""
        import importlib.util
        import os

        spec = importlib.util.spec_from_file_location(
            'helper', os.path.join(os.path.dirname(__file__), '../../src/opensearch/helper.py')
        )
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        convert_search_results_to_csv = helper.convert_search_results_to_csv

        # Empty search results
        assert convert_search_results_to_csv({}) == 'No search results to convert'
        assert convert_search_results_to_csv(None) == 'No search results to convert'

        # No hits
        search_results = {'hits': {'hits': []}}
        result = convert_search_results_to_csv(search_results)
        assert 'No search results to convert' in result

        # Only aggregations with empty hits
        search_results = {'hits': {'hits': []}, 'aggregations': {'count': {'value': 0}}}
        result = convert_search_results_to_csv(search_results)
        assert 'count' in result
        assert '0' in result

    def test_normalize_scientific_notation(self):
        import importlib.util
        import os

        spec = importlib.util.spec_from_file_location(
            'helper', os.path.join(os.path.dirname(__file__), '../../src/opensearch/helper.py')
        )
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        normalize_scientific_notation = helper.normalize_scientific_notation
        query_dsl = {'query': {'range': {'timestamp': {'gte': 1732693003e3, 'lte': 173.5}}}}
        result = normalize_scientific_notation(query_dsl)
        assert '1732693003000' in json.dumps(result)
        assert '173.5' in json.dumps(result)


class TestValidateJsonString:
    def setup_method(self):
        from opensearch.helper import validate_json_string

        self.validate = validate_json_string

    # --- valid inputs (should not raise) ---

    def test_valid_object(self):
        self.validate('{"query": {"match_all": {}}}')

    def test_valid_empty_object(self):
        self.validate('{}')

    def test_valid_array(self):
        self.validate('[1, 2, 3]')

    def test_valid_nested_object(self):
        self.validate('{"a": {"b": {"c": 42}}}')

    def test_valid_with_whitespace(self):
        self.validate('  { "key" : "value" }  ')

    def test_valid_with_newlines(self):
        self.validate('{\n  "query": {\n    "match_all": {}\n  }\n}')

    def test_valid_types(self):
        # booleans, null, numbers
        self.validate('{"flag": true, "missing": null, "count": 99}')

    def test_valid_search_config_query(self):
        self.validate('{"query":{"match":{"title":"%SearchText%"}}}')

    # --- invalid inputs (should raise ValueError) ---

    def test_invalid_trailing_comma(self):
        with pytest.raises(ValueError) as exc_info:
            self.validate('{"query": {"match_all": {}},}')
        assert 'query is not valid JSON' in str(exc_info.value)

    def test_invalid_single_quotes(self):
        with pytest.raises(ValueError) as exc_info:
            self.validate("{'key': 'value'}")
        assert 'query is not valid JSON' in str(exc_info.value)

    def test_invalid_unquoted_key(self):
        with pytest.raises(ValueError) as exc_info:
            self.validate('{key: "value"}')
        assert 'query is not valid JSON' in str(exc_info.value)

    def test_invalid_unclosed_brace(self):
        with pytest.raises(ValueError) as exc_info:
            self.validate('{"query": {"match_all": {}')
        assert 'query is not valid JSON' in str(exc_info.value)

    def test_invalid_empty_string(self):
        with pytest.raises(ValueError) as exc_info:
            self.validate('')
        assert 'query is not valid JSON' in str(exc_info.value)

    def test_invalid_plain_text(self):
        with pytest.raises(ValueError) as exc_info:
            self.validate('not json at all')
        assert 'query is not valid JSON' in str(exc_info.value)

    def test_invalid_bad_escape(self):
        with pytest.raises(ValueError) as exc_info:
            self.validate('{"key": "bad\\escape"}')
        assert 'query is not valid JSON' in str(exc_info.value)

    def test_error_message_includes_location(self):
        """Error message should contain line and column so the problem is easy to pinpoint."""
        with pytest.raises(ValueError) as exc_info:
            self.validate('{"a": 1,\n"b": 2,\n"c": }')
        msg = str(exc_info.value)
        assert 'line' in msg
        assert 'col' in msg

    def test_error_message_format(self):
        """ValueError should be raised (not json.JSONDecodeError directly)."""
        with pytest.raises(ValueError):
            self.validate('{bad}')

    def test_cause_is_json_decode_error(self):
        """The ValueError should chain the original JSONDecodeError."""
        import json as _json

        with pytest.raises(ValueError) as exc_info:
            self.validate('{bad}')
        assert isinstance(exc_info.value.__cause__, _json.JSONDecodeError)


class TestSearchConfigurationHelpers:
    def setup_method(self):
        """Setup that runs before each test method."""
        from opensearch.helper import (
            create_search_configuration,
            delete_search_configuration,
            get_search_configuration,
        )

        self.create_search_configuration = create_search_configuration
        self.get_search_configuration = get_search_configuration
        self.delete_search_configuration = delete_search_configuration

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_create_search_configuration(self, mock_get_client):
        """Test create_search_configuration calls put_search_configurations with correct body."""
        from tools.tool_params import CreateSearchConfigurationArgs

        mock_response = {'_id': 'cfg-1', 'result': 'created'}
        mock_client = AsyncMock()
        mock_client.plugins = AsyncMock()
        mock_client.plugins.search_relevance = AsyncMock()
        mock_client.plugins.search_relevance.put_search_configurations = AsyncMock(
            return_value=mock_response
        )

        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        args = CreateSearchConfigurationArgs(
            name='my-config',
            index='my-index',
            query='{"query":{"match":{"title":"%SearchText%"}}}',
            opensearch_cluster_name='',
        )
        result = await self.create_search_configuration(args)

        assert result == mock_response
        mock_client.plugins.search_relevance.put_search_configurations.assert_called_once_with(
            body={
                'name': 'my-config',
                'index': 'my-index',
                'query': '{"query":{"match":{"title":"%SearchText%"}}}',
            }
        )

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_get_search_configuration(self, mock_get_client):
        """Test get_search_configuration calls get_search_configurations with correct ID."""
        from tools.tool_params import GetSearchConfigurationArgs

        mock_response = {'_id': 'cfg-1', '_source': {'name': 'my-config', 'index': 'my-index'}}
        mock_client = AsyncMock()
        mock_client.plugins = AsyncMock()
        mock_client.plugins.search_relevance = AsyncMock()
        mock_client.plugins.search_relevance.get_search_configurations = AsyncMock(
            return_value=mock_response
        )

        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        args = GetSearchConfigurationArgs(
            search_configuration_id='cfg-1', opensearch_cluster_name=''
        )
        result = await self.get_search_configuration(args)

        assert result == mock_response
        mock_client.plugins.search_relevance.get_search_configurations.assert_called_once_with(
            search_configuration_id='cfg-1'
        )

    @pytest.mark.asyncio
    @patch('opensearch.client.get_opensearch_client')
    async def test_delete_search_configuration(self, mock_get_client):
        """Test delete_search_configuration calls delete_search_configurations with correct ID."""
        from tools.tool_params import DeleteSearchConfigurationArgs

        mock_response = {'result': 'deleted'}
        mock_client = AsyncMock()
        mock_client.plugins = AsyncMock()
        mock_client.plugins.search_relevance = AsyncMock()
        mock_client.plugins.search_relevance.delete_search_configurations = AsyncMock(
            return_value=mock_response
        )

        mock_get_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = AsyncMock(return_value=None)

        args = DeleteSearchConfigurationArgs(
            search_configuration_id='cfg-1', opensearch_cluster_name=''
        )
        result = await self.delete_search_configuration(args)

        assert result == mock_response
        mock_client.plugins.search_relevance.delete_search_configurations.assert_called_once_with(
            search_configuration_id='cfg-1'
        )


class TestVersionCacheHeaderAuthBypass:
    """When OPENSEARCH_HEADER_AUTH=true the version fetch must bypass the cache.

    The real target URL comes from the per-request opensearch-url header, which the
    cache key (env/args URL) cannot see — caching would bleed one cluster's version
    to another. Regression test for the adversarial-review MAJOR.
    """

    def setup_method(self):
        from opensearch.version_cache import clear_cache

        clear_cache()

    @pytest.mark.asyncio
    async def test_header_auth_bypasses_cache(self, monkeypatch):
        import opensearch.helper as helper_mod
        from tools.tool_params import baseToolArgs

        monkeypatch.setenv('OPENSEARCH_HEADER_AUTH', 'true')

        calls = {'n': 0}

        async def fake_fetch(_args):
            calls['n'] += 1
            from semver import Version

            return Version.parse('2.0.0')

        monkeypatch.setattr(helper_mod, '_fetch_opensearch_version', fake_fetch)

        args = baseToolArgs(opensearch_cluster_name='')
        await helper_mod.get_opensearch_version(args)
        await helper_mod.get_opensearch_version(args)

        # Both calls fetch (no caching) because the real URL is per-request header.
        assert calls['n'] == 2

    @pytest.mark.asyncio
    async def test_non_header_auth_uses_cache(self, monkeypatch):
        import opensearch.helper as helper_mod
        from tools.tool_params import baseToolArgs

        monkeypatch.delenv('OPENSEARCH_HEADER_AUTH', raising=False)
        monkeypatch.setenv('OPENSEARCH_URL', 'https://fixed-cluster:9200')

        calls = {'n': 0}

        async def fake_fetch(_args):
            calls['n'] += 1
            from semver import Version

            return Version.parse('2.0.0')

        monkeypatch.setattr(helper_mod, '_fetch_opensearch_version', fake_fetch)

        args = baseToolArgs(opensearch_cluster_name='')
        await helper_mod.get_opensearch_version(args)
        await helper_mod.get_opensearch_version(args)

        # Cached: only one underlying fetch for the same static URL.
        assert calls['n'] == 1


class TestVersionCacheMultiModeHeaderAuthBypass:
    """Multi-mode per-cluster header-auth must also bypass the version cache.

    Regression test for review #3 MAJOR: the single-mode bypass (OPENSEARCH_HEADER_AUTH)
    did not cover multi mode, where header auth is enabled per-cluster via
    cluster_info.opensearch_header_auth and the URL comes from a per-request header.
    """

    def setup_method(self):
        from opensearch.version_cache import clear_cache

        clear_cache()

    @pytest.mark.asyncio
    async def test_multi_mode_header_auth_cluster_bypasses_cache(self, monkeypatch):
        import opensearch.helper as helper_mod
        from mcp_server_opensearch import clusters_information
        from mcp_server_opensearch.clusters_information import ClusterInfo
        from tools.tool_params import baseToolArgs

        monkeypatch.setattr('mcp_server_opensearch.global_state.get_mode', lambda: 'multi')
        # A cluster configured with header auth -> URL is per-request -> must bypass cache.
        monkeypatch.setitem(
            clusters_information.cluster_registry,
            'hdr-cluster',
            ClusterInfo(opensearch_url='https://placeholder:9200', opensearch_header_auth=True),
        )

        calls = {'n': 0}

        async def fake_fetch(_args):
            from semver import Version

            calls['n'] += 1
            return Version.parse('2.0.0')

        monkeypatch.setattr(helper_mod, '_fetch_opensearch_version', fake_fetch)

        args = baseToolArgs(opensearch_cluster_name='hdr-cluster')
        await helper_mod.get_opensearch_version(args)
        await helper_mod.get_opensearch_version(args)

        assert calls['n'] == 2  # bypassed: fetched each time

    @pytest.mark.asyncio
    async def test_multi_mode_non_header_cluster_uses_cache(self, monkeypatch):
        import opensearch.helper as helper_mod
        from mcp_server_opensearch import clusters_information
        from mcp_server_opensearch.clusters_information import ClusterInfo
        from tools.tool_params import baseToolArgs

        monkeypatch.setattr('mcp_server_opensearch.global_state.get_mode', lambda: 'multi')
        monkeypatch.setitem(
            clusters_information.cluster_registry,
            'fixed-cluster',
            ClusterInfo(opensearch_url='https://fixed:9200', opensearch_header_auth=False),
        )

        calls = {'n': 0}

        async def fake_fetch(_args):
            from semver import Version

            calls['n'] += 1
            return Version.parse('2.0.0')

        monkeypatch.setattr(helper_mod, '_fetch_opensearch_version', fake_fetch)

        args = baseToolArgs(opensearch_cluster_name='fixed-cluster')
        await helper_mod.get_opensearch_version(args)
        await helper_mod.get_opensearch_version(args)

        assert calls['n'] == 1  # cached: fetched once for the static cluster

# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Validation-fidelity tests for the 4 static (ex-generated) tool arg models.

Pins the exact validation behavior the old OpenAPI generator produced (it used
create_model with (str, None) path/query fields and (Any, None) body): omission and
string values are accepted, an explicit null on a path/query field is REJECTED, and an
explicit null body is ACCEPTED. A naive Optional[str]=None would wrongly accept null.
"""

import pytest
from pydantic import ValidationError
from tools.domains.generated.params import (
    ClusterHealthArgs,
    CountArgs,
    ExplainArgs,
    MsearchArgs,
)


class TestGeneratedParamsValidation:
    def test_omitting_index_is_allowed(self):
        assert MsearchArgs(opensearch_cluster_name='').index is None

    def test_string_index_is_allowed(self):
        assert MsearchArgs(opensearch_cluster_name='', index='logs').index == 'logs'

    def test_explicit_null_index_is_rejected(self):
        # (str, None) typing rejects explicit null — matches the generator.
        with pytest.raises(ValidationError):
            MsearchArgs(opensearch_cluster_name='', index=None)

    def test_explicit_null_id_is_rejected(self):
        with pytest.raises(ValidationError):
            ExplainArgs(opensearch_cluster_name='', id=None)

    def test_explicit_null_body_is_allowed(self):
        # body is typed Any -> null is accepted (matches the generator).
        assert MsearchArgs(opensearch_cluster_name='', body=None).body is None

    def test_dict_body_is_allowed(self):
        assert CountArgs(opensearch_cluster_name='', body={'q': 1}).body == {'q': 1}

    def test_cluster_health_explicit_null_index_rejected(self):
        with pytest.raises(ValidationError):
            ClusterHealthArgs(opensearch_cluster_name='', index=None)

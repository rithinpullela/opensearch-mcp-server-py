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


class TestGeneratedParamsBaseArgTyping:
    """Base connection args use their real baseToolArgs types (DECISION_LOG D15).

    The old generator coerced every base field to str; the static models inherit the
    true types via __base__=baseToolArgs. This is a deliberate, more-correct change —
    the 4 ex-generated tools now type-validate base args like every other tool.
    """

    def test_bool_base_arg_accepts_real_bool(self):
        # aws_opensearch_serverless is a real bool now (generator typed it str).
        m = MsearchArgs(opensearch_cluster_name='', aws_opensearch_serverless=True)
        assert m.aws_opensearch_serverless is True

    def test_int_base_arg_accepts_real_int(self):
        # opensearch_timeout is a real int now (generator typed it str).
        m = CountArgs(opensearch_cluster_name='', opensearch_timeout=30)
        assert m.opensearch_timeout == 30

    def test_base_args_match_basetoolargs_types(self):
        from tools.tool_params import baseToolArgs

        for name in ('aws_opensearch_serverless', 'opensearch_timeout', 'opensearch_no_auth'):
            assert (
                ExplainArgs.model_fields[name].annotation
                == baseToolArgs.model_fields[name].annotation
            )

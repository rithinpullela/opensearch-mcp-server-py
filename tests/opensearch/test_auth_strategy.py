# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from opensearch.auth_strategy import (
    AuthenticationError,
    BasicAuth,
    BearerToken,
    HeaderAWSCreds,
    IAMRoleAssumed,
    NoAuth,
    ProfileAWSCreds,
    resolve_auth_strategy,
)


class TestEachLevelInIsolation:
    """Each of the 6 auth levels selected with only its own params present."""

    def test_level1_no_auth(self):
        result = resolve_auth_strategy(opensearch_no_auth=True)
        assert isinstance(result, NoAuth)

    def test_level2_bearer(self):
        result = resolve_auth_strategy(bearer_auth_header='Bearer abc123')
        assert isinstance(result, BearerToken)
        assert result.bearer_auth_header == 'Bearer abc123'

    def test_level3_header_aws_full_triple(self):
        result = resolve_auth_strategy(
            aws_access_key_id='AKIA',
            aws_secret_access_key='secret',
            aws_region='us-east-1',
            aws_session_token='token',
        )
        assert isinstance(result, HeaderAWSCreds)
        assert result.access_key == 'AKIA'
        assert result.secret_key == 'secret'
        assert result.region == 'us-east-1'
        assert result.session_token == 'token'
        assert result.service == 'es'

    def test_level4_iam_role(self):
        result = resolve_auth_strategy(
            iam_arn='arn:aws:iam::123456789012:role/my-role',
            aws_region='us-west-2',
            profile='my-profile',
        )
        assert isinstance(result, IAMRoleAssumed)
        assert result.iam_arn == 'arn:aws:iam::123456789012:role/my-role'
        assert result.region == 'us-west-2'
        assert result.profile == 'my-profile'
        assert result.service == 'es'

    def test_level5_basic(self):
        result = resolve_auth_strategy(opensearch_username='admin', opensearch_password='pw')
        assert isinstance(result, BasicAuth)
        assert result.username == 'admin'
        assert result.password == 'pw'

    def test_level6_ambient_fallthrough(self):
        result = resolve_auth_strategy(aws_region='eu-central-1', profile='ambient-profile')
        assert isinstance(result, ProfileAWSCreds)
        assert result.region == 'eu-central-1'
        assert result.profile == 'ambient-profile'
        assert result.service == 'es'


class TestServerlessServiceName:
    """Serverless mode selects the 'aoss' SigV4 service for AWS strategies."""

    def test_header_aws_serverless_service(self):
        result = resolve_auth_strategy(
            aws_access_key_id='AKIA',
            aws_secret_access_key='secret',
            aws_region='us-east-1',
            is_serverless_mode=True,
        )
        assert isinstance(result, HeaderAWSCreds)
        assert result.service == 'aoss'

    def test_iam_serverless_service(self):
        result = resolve_auth_strategy(
            iam_arn='arn:aws:iam::1:role/r',
            aws_region='us-east-1',
            is_serverless_mode=True,
        )
        assert isinstance(result, IAMRoleAssumed)
        assert result.service == 'aoss'

    def test_ambient_serverless_service(self):
        result = resolve_auth_strategy(aws_region='us-east-1', is_serverless_mode=True)
        assert isinstance(result, ProfileAWSCreds)
        assert result.service == 'aoss'

    def test_default_non_serverless_service_is_es(self):
        result = resolve_auth_strategy(aws_region='us-east-1')
        assert isinstance(result, ProfileAWSCreds)
        assert result.service == 'es'


class TestPrecedence:
    """Precedence ordering is contract: higher levels win over lower ones."""

    def test_no_auth_beats_everything(self):
        result = resolve_auth_strategy(
            opensearch_no_auth=True,
            bearer_auth_header='Bearer x',
            aws_access_key_id='AKIA',
            aws_secret_access_key='secret',
            aws_region='us-east-1',
            iam_arn='arn:aws:iam::1:role/r',
            opensearch_username='admin',
            opensearch_password='pw',
        )
        assert isinstance(result, NoAuth)

    def test_bearer_beats_header_aws(self):
        result = resolve_auth_strategy(
            bearer_auth_header='Bearer x',
            aws_access_key_id='AKIA',
            aws_secret_access_key='secret',
            aws_region='us-east-1',
        )
        assert isinstance(result, BearerToken)

    def test_bearer_beats_iam_basic_and_ambient(self):
        result = resolve_auth_strategy(
            bearer_auth_header='Bearer x',
            iam_arn='arn:aws:iam::1:role/r',
            opensearch_username='admin',
            opensearch_password='pw',
            aws_region='us-east-1',
        )
        assert isinstance(result, BearerToken)

    def test_header_aws_beats_iam(self):
        result = resolve_auth_strategy(
            aws_access_key_id='AKIA',
            aws_secret_access_key='secret',
            aws_region='us-east-1',
            iam_arn='arn:aws:iam::1:role/r',
        )
        assert isinstance(result, HeaderAWSCreds)

    def test_header_aws_beats_basic(self):
        result = resolve_auth_strategy(
            aws_access_key_id='AKIA',
            aws_secret_access_key='secret',
            aws_region='us-east-1',
            opensearch_username='admin',
            opensearch_password='pw',
        )
        assert isinstance(result, HeaderAWSCreds)

    def test_header_aws_beats_ambient(self):
        # All three header creds present plus a region that would also satisfy
        # ambient: header-AWS must win.
        result = resolve_auth_strategy(
            aws_access_key_id='AKIA',
            aws_secret_access_key='secret',
            aws_region='us-east-1',
        )
        assert isinstance(result, HeaderAWSCreds)

    def test_iam_beats_basic(self):
        result = resolve_auth_strategy(
            iam_arn='arn:aws:iam::1:role/r',
            aws_region='us-east-1',
            opensearch_username='admin',
            opensearch_password='pw',
        )
        assert isinstance(result, IAMRoleAssumed)

    def test_iam_beats_ambient(self):
        result = resolve_auth_strategy(
            iam_arn='arn:aws:iam::1:role/r',
            aws_region='us-east-1',
        )
        assert isinstance(result, IAMRoleAssumed)

    def test_basic_beats_ambient(self):
        # Basic auth requires no region; even with a region present, basic wins
        # over the ambient fallthrough.
        result = resolve_auth_strategy(
            opensearch_username='admin',
            opensearch_password='pw',
            aws_region='us-east-1',
        )
        assert isinstance(result, BasicAuth)


class TestPartialAWSCredsFailSecure:
    """Fail-secure: partial header AWS creds raise instead of falling through."""

    def test_access_key_and_secret_without_region_raises(self):
        with pytest.raises(AuthenticationError):
            resolve_auth_strategy(
                aws_access_key_id='AKIA',
                aws_secret_access_key='secret',
            )

    def test_access_key_and_region_without_secret_raises(self):
        with pytest.raises(AuthenticationError):
            resolve_auth_strategy(
                aws_access_key_id='AKIA',
                aws_region='us-east-1',
            )

    def test_secret_and_region_without_access_key_raises(self):
        with pytest.raises(AuthenticationError):
            resolve_auth_strategy(
                aws_secret_access_key='secret',
                aws_region='us-east-1',
            )

    def test_only_access_key_raises(self):
        with pytest.raises(AuthenticationError):
            resolve_auth_strategy(aws_access_key_id='AKIA')

    def test_only_secret_key_raises(self):
        with pytest.raises(AuthenticationError):
            resolve_auth_strategy(aws_secret_access_key='secret')

    def test_partial_creds_do_not_fall_through_to_basic(self):
        # Even when valid basic creds are present, a partial AWS triple must
        # fail secure rather than silently using a lower-precedence strategy.
        with pytest.raises(AuthenticationError):
            resolve_auth_strategy(
                aws_access_key_id='AKIA',
                aws_secret_access_key='secret',
                opensearch_username='admin',
                opensearch_password='pw',
            )

    def test_partial_creds_do_not_fall_through_to_ambient(self):
        # access_key + secret_key but region omitted: must NOT silently become
        # ambient identity even though region would normally drive ambient.
        with pytest.raises(AuthenticationError):
            resolve_auth_strategy(
                aws_access_key_id='AKIA',
                aws_secret_access_key='secret',
            )

    def test_region_alone_is_not_a_partial_credential(self):
        # Region is shared with IAM/ambient; supplying only a region must route
        # to the ambient strategy, NOT raise as a partial header credential.
        result = resolve_auth_strategy(aws_region='us-east-1')
        assert isinstance(result, ProfileAWSCreds)

    def test_region_alone_with_iam_routes_to_iam(self):
        result = resolve_auth_strategy(
            iam_arn='arn:aws:iam::1:role/r',
            aws_region='us-east-1',
        )
        assert isinstance(result, IAMRoleAssumed)


class TestRegionRequirements:
    """Region is required for IAM and ambient AWS strategies."""

    def test_iam_without_region_raises(self):
        with pytest.raises(AuthenticationError):
            resolve_auth_strategy(iam_arn='arn:aws:iam::1:role/r')

    def test_iam_blank_region_raises(self):
        with pytest.raises(AuthenticationError):
            resolve_auth_strategy(iam_arn='arn:aws:iam::1:role/r', aws_region='   ')

    def test_ambient_without_region_raises(self):
        with pytest.raises(AuthenticationError):
            resolve_auth_strategy()

    def test_ambient_blank_region_raises(self):
        with pytest.raises(AuthenticationError):
            resolve_auth_strategy(aws_region='   ')


class TestNormalization:
    """Whitespace handling matches the inline ladder's .strip() behavior."""

    def test_header_region_stripped(self):
        result = resolve_auth_strategy(
            aws_access_key_id='AKIA',
            aws_secret_access_key='secret',
            aws_region='  us-east-1  ',
        )
        assert isinstance(result, HeaderAWSCreds)
        assert result.region == 'us-east-1'

    def test_iam_arn_and_region_stripped(self):
        result = resolve_auth_strategy(
            iam_arn='  arn:aws:iam::1:role/r  ',
            aws_region='  us-east-1  ',
        )
        assert isinstance(result, IAMRoleAssumed)
        assert result.iam_arn == 'arn:aws:iam::1:role/r'
        assert result.region == 'us-east-1'

    def test_ambient_region_stripped(self):
        result = resolve_auth_strategy(aws_region='  eu-west-1  ')
        assert isinstance(result, ProfileAWSCreds)
        assert result.region == 'eu-west-1'


class TestStrategyImmutability:
    """Strategy dataclasses are frozen (immutable)."""

    def test_no_auth_frozen(self):
        result = NoAuth()
        with pytest.raises(Exception):
            result.x = 1  # type: ignore[attr-defined]

    def test_basic_auth_frozen(self):
        result = BasicAuth(username='u', password='p')
        with pytest.raises(Exception):
            result.username = 'other'  # type: ignore[misc]

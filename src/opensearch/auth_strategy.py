# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed authentication-strategy resolver for OpenSearch client creation.

This module extracts the 6-level authentication ladder that currently lives
inline in ``_create_opensearch_client`` (``src/opensearch/client.py``) into a
single, pure decision function. It does NOT build clients, open connections, or
perform any I/O; it only decides *which* authentication strategy applies to a
set of already-resolved connection parameters and returns that strategy with the
parameters needed to apply it.

The precedence order is load-bearing contract (verified against
``client.py:607-707`` and exercised by ``integration_tests/auth/*``):

1. No authentication (``opensearch_no_auth``)
2. Bearer token (``bearer_auth_header``)
3. Header AWS credentials (requires ALL of access key, secret key, region)
4. IAM role assumption (``iam_arn``)
5. Basic authentication (username + password)
6. Ambient AWS credentials (fallthrough)

Fail-secure (design decision O4 / row 6): if any of the header AWS credential
triple {access_key, secret_key, region} is present but not all three, the
resolver raises :class:`AuthenticationError` instead of silently falling through
to ambient AWS identity.
"""

from dataclasses import dataclass
from typing import Optional, Union


try:
    # Reuse the canonical exception so callers catch the same type the inline
    # ladder raised. The import is cheap (client.py is already imported wherever
    # the resolver is wired in), so prefer it over a duplicate definition.
    from opensearch.client import AuthenticationError
except Exception:  # pragma: no cover - fallback for import-order edge cases
    from opensearch.connection import OpenSearchClientError

    class AuthenticationError(OpenSearchClientError):
        """Exception raised when authentication fails.

        Local fallback mirroring ``opensearch.client.AuthenticationError`` with
        identical name and semantics; used only if the canonical class cannot be
        imported. See integrationNotes.
        """

        pass


@dataclass(frozen=True)
class NoAuth:
    """Connect without any authentication (level 1)."""

    pass


@dataclass(frozen=True)
class BearerToken:
    """Authenticate using an ``Authorization: Bearer`` header (level 2).

    Attributes:
        bearer_auth_header: The raw Authorization header value to send.
    """

    bearer_auth_header: str


@dataclass(frozen=True)
class HeaderAWSCreds:
    """Authenticate with AWS SigV4 using credentials supplied via headers (level 3).

    Selected only when all of ``access_key``, ``secret_key`` and ``region`` are
    present.

    Attributes:
        access_key: AWS access key ID.
        secret_key: AWS secret access key.
        region: AWS region used to sign requests.
        session_token: Optional AWS session token.
        service: SigV4 service name (``'es'`` or ``'aoss'``).
    """

    access_key: str
    secret_key: str
    region: str
    session_token: Optional[str]
    service: str


@dataclass(frozen=True)
class IAMRoleAssumed:
    """Authenticate by assuming an IAM role and signing with SigV4 (level 4).

    Attributes:
        iam_arn: The IAM role ARN to assume.
        region: AWS region used both for STS and to sign requests.
        profile: AWS profile name used to create the boto3 session (may be '').
        service: SigV4 service name (``'es'`` or ``'aoss'``).
    """

    iam_arn: str
    region: str
    profile: str
    service: str


@dataclass(frozen=True)
class BasicAuth:
    """Authenticate with HTTP basic credentials (level 5).

    Attributes:
        username: Basic-auth username.
        password: Basic-auth password.
    """

    username: str
    password: str


@dataclass(frozen=True)
class ProfileAWSCreds:
    """Authenticate with ambient AWS credentials from the boto3 session (level 6).

    This is the fallthrough strategy used when no higher-precedence credentials
    are supplied. The credentials themselves are resolved from the boto3 session
    (optionally created from ``profile``) at apply time, not here.

    Attributes:
        region: AWS region used to sign requests.
        profile: AWS profile name used to create the boto3 session (may be '').
        service: SigV4 service name (``'es'`` or ``'aoss'``).
    """

    region: str
    profile: str
    service: str


AuthStrategy = Union[
    NoAuth,
    BasicAuth,
    BearerToken,
    HeaderAWSCreds,
    IAMRoleAssumed,
    ProfileAWSCreds,
]


def _is_blank(value: Optional[str]) -> bool:
    """Return True when a string value is None, empty, or whitespace-only."""
    return value is None or (isinstance(value, str) and not value.strip())


def resolve_auth_strategy(
    *,
    opensearch_no_auth: bool = False,
    bearer_auth_header: Optional[str] = None,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    aws_region: Optional[str] = None,
    aws_session_token: Optional[str] = None,
    iam_arn: str = '',
    opensearch_username: str = '',
    opensearch_password: str = '',
    profile: str = '',
    is_serverless_mode: bool = False,
) -> AuthStrategy:
    """Resolve which authentication strategy applies to the given connection params.

    This is a PURE decision function: it does no I/O, builds no clients, and only
    inspects the already-resolved connection parameters (the same values
    ``_create_opensearch_client`` reads). The precedence order reproduces
    ``client.py:607-707`` exactly:

    1. ``opensearch_no_auth`` truthy -> :class:`NoAuth`.
    2. ``bearer_auth_header`` truthy -> :class:`BearerToken`.
    3. ALL of ``aws_access_key_id``, ``aws_secret_access_key``, ``aws_region``
       present -> :class:`HeaderAWSCreds`.
    4. ``iam_arn`` (non-blank) -> :class:`IAMRoleAssumed` (region required).
    5. ``opensearch_username`` and ``opensearch_password`` both present ->
       :class:`BasicAuth`.
    6. Otherwise -> :class:`ProfileAWSCreds` (ambient AWS fallthrough; region
       required).

    Fail-secure (design O4): between levels 2 and 3, if header-credential-
    specific material (``aws_access_key_id`` and/or ``aws_secret_access_key``)
    is present but the full {access_key, secret_key, region} triple is not,
    raise :class:`AuthenticationError` rather than silently continuing to a
    lower level / ambient identity. A region supplied on its own is NOT a
    partial header credential: it is the legitimate input for the IAM (level 4)
    and ambient (level 6) strategies, so region-alone does not trigger the
    guard.

    Args:
        opensearch_no_auth: If truthy, select :class:`NoAuth`.
        bearer_auth_header: Authorization Bearer header value, if any.
        aws_access_key_id: AWS access key ID from headers, if any.
        aws_secret_access_key: AWS secret access key from headers, if any.
        aws_region: AWS region (used by header AWS, IAM, and ambient strategies).
        aws_session_token: Optional AWS session token for header AWS credentials.
        iam_arn: IAM role ARN for role-based authentication.
        opensearch_username: Username for basic authentication.
        opensearch_password: Password for basic authentication.
        profile: AWS profile name used to build the boto3 session.
        is_serverless_mode: Whether the target is OpenSearch Serverless; selects
            the SigV4 service name (``'aoss'`` vs ``'es'``).

    Returns:
        AuthStrategy: The resolved strategy dataclass.

    Raises:
        AuthenticationError: If header AWS credentials are partially supplied
            (an access key and/or secret key without the full triple), or if a
            region is required for the selected AWS strategy (IAM or ambient)
            but missing.
    """
    service_name = 'aoss' if is_serverless_mode else 'es'

    # 1. No authentication.
    if opensearch_no_auth:
        return NoAuth()

    # 2. Header-based Authorization (Bearer token).
    if bearer_auth_header:
        return BearerToken(bearer_auth_header=bearer_auth_header)

    # 3. Header-based AWS credentials (highest priority when fully provided).
    # The inline ladder selects this branch only when all three are truthy
    # (client.py:630). Fail-secure (design O4): a partial triple must raise,
    # never fall through to ambient identity.
    #
    # Note on the trigger: ``aws_region`` is shared with the IAM (level 4) and
    # ambient (level 6) strategies, which legitimately accept a region with no
    # access/secret key. So region-alone must NOT count as a partial header
    # credential (doing so would break the IAM/profile contract the design
    # preserves). The partial-credentials guard therefore fires only when the
    # header-credential-specific material (access key and/or secret key) is
    # present but the full {access_key, secret_key, region} triple is not.
    has_access_key = bool(aws_access_key_id)
    has_secret_key = bool(aws_secret_access_key)
    has_region = bool(aws_region)

    if has_access_key and has_secret_key and has_region:
        if _is_blank(aws_region):
            raise AuthenticationError('AWS region is required for header-based authentication')
        return HeaderAWSCreds(
            access_key=aws_access_key_id,
            secret_key=aws_secret_access_key,
            region=aws_region.strip(),
            session_token=aws_session_token,
            service=service_name,
        )
    if has_access_key or has_secret_key:
        raise AuthenticationError(
            'Incomplete AWS header credentials: all of aws_access_key_id, '
            'aws_secret_access_key, and aws_region are required when any of '
            'aws_access_key_id or aws_secret_access_key is provided'
        )

    # 4. IAM role authentication.
    if iam_arn and iam_arn.strip():
        if _is_blank(aws_region):
            raise AuthenticationError('AWS region is required for IAM role authentication')
        return IAMRoleAssumed(
            iam_arn=iam_arn.strip(),
            region=aws_region.strip(),
            profile=profile,
            service=service_name,
        )

    # 5. Basic authentication.
    if opensearch_username and opensearch_password:
        return BasicAuth(username=opensearch_username, password=opensearch_password)

    # 6. Ambient AWS credentials (fallthrough).
    if _is_blank(aws_region):
        raise AuthenticationError('AWS region is required for AWS credentials authentication')
    return ProfileAWSCreds(region=aws_region.strip(), profile=profile, service=service_name)

# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import importlib
import pytest
import sys


# Ensure ``src`` is importable as a top-level package directory, matching how the
# rest of the suite imports modules (e.g. ``from settings import Settings``).
SRC_PATH = str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'src')
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

settings_module = importlib.import_module('settings')
Settings = settings_module.Settings
parse_bool_string = settings_module.parse_bool_string
parse_ssl_verify = settings_module.parse_ssl_verify
DEFAULT_MEMORY_INDEX_NAME = settings_module.DEFAULT_MEMORY_INDEX_NAME


# Every env-var alias the model reads, with no env set, must equal these defaults.
# This pins today's behavior exactly.
EXPECTED_DEFAULTS = {
    'opensearch_url': '',
    'opensearch_username': '',
    'opensearch_password': '',
    'opensearch_no_auth': False,
    'aws_iam_arn': '',
    'aws_profile': '',
    'aws_region': '',
    'aws_opensearch_serverless': False,
    'opensearch_header_auth': False,
    'opensearch_timeout': None,
    'opensearch_ssl_verify': True,
    'opensearch_ca_cert_path': '',
    'opensearch_client_cert_path': '',
    'opensearch_client_key_path': '',
    'opensearch_max_response_size': None,
    'opensearch_query_timeout': '',
    'opensearch_dynamic_connection': '',
    'opensearch_enabled_tools': '',
    'opensearch_disabled_tools': '',
    'opensearch_tool_categories': '',
    'opensearch_enabled_categories': '',
    'opensearch_disabled_categories': '',
    'opensearch_enabled_tools_regex': '',
    'opensearch_disabled_tools_regex': '',
    'opensearch_settings_allow_write': True,
    'opensearch_settings_allow_write_categories': '',
    'memory_tools_enabled': False,
    'memory_index_name': DEFAULT_MEMORY_INDEX_NAME,
    'memory_user_id': '',
    'memory_agent_id': '',
    'opensearch_memory_container_id': '',
    'aws_opensearch_domain_name': '',
    'aws_opensearch_collection_id': '',
    'opensearch_memory_monitor_interval': 60,
}

# Maps each field name -> the exact current env-var alias and a representative value.
FIELD_TO_ENV = {
    'opensearch_url': ('OPENSEARCH_URL', 'https://example.com:9200'),
    'opensearch_username': ('OPENSEARCH_USERNAME', 'admin'),
    'opensearch_password': ('OPENSEARCH_PASSWORD', 's3cr3t'),
    'aws_iam_arn': ('AWS_IAM_ARN', 'arn:aws:iam::123456789012:role/Role'),
    'aws_profile': ('AWS_PROFILE', 'my-profile'),
    'aws_region': ('AWS_REGION', 'us-east-2'),
    'opensearch_ca_cert_path': ('OPENSEARCH_CA_CERT_PATH', '/tmp/ca.crt'),
    'opensearch_client_cert_path': ('OPENSEARCH_CLIENT_CERT_PATH', '/tmp/tls.crt'),
    'opensearch_client_key_path': ('OPENSEARCH_CLIENT_KEY_PATH', '/tmp/tls.key'),
    'opensearch_query_timeout': ('OPENSEARCH_QUERY_TIMEOUT', '30s'),
    'opensearch_dynamic_connection': ('OPENSEARCH_DYNAMIC_CONNECTION', '1'),
    'opensearch_enabled_tools': ('OPENSEARCH_ENABLED_TOOLS', 'SearchIndexTool'),
    'opensearch_disabled_tools': ('OPENSEARCH_DISABLED_TOOLS', 'DeleteIndexTool'),
    'opensearch_tool_categories': ('OPENSEARCH_TOOL_CATEGORIES', 'search'),
    'opensearch_enabled_categories': ('OPENSEARCH_ENABLED_CATEGORIES', 'search'),
    'opensearch_disabled_categories': ('OPENSEARCH_DISABLED_CATEGORIES', 'admin'),
    'opensearch_enabled_tools_regex': ('OPENSEARCH_ENABLED_TOOLS_REGEX', 'Search.*'),
    'opensearch_disabled_tools_regex': ('OPENSEARCH_DISABLED_TOOLS_REGEX', 'debug.*'),
    'opensearch_settings_allow_write_categories': (
        'OPENSEARCH_SETTINGS_ALLOW_WRITE_CATEGORIES',
        'search_relevance',
    ),
    'memory_index_name': ('MEMORY_INDEX_NAME', 'custom-memory'),
    'memory_user_id': ('MEMORY_USER_ID', 'user-1'),
    'memory_agent_id': ('MEMORY_AGENT_ID', 'agent-1'),
    'opensearch_memory_container_id': ('OPENSEARCH_MEMORY_CONTAINER_ID', 'container-1'),
    'aws_opensearch_domain_name': ('AWS_OPENSEARCH_DOMAIN_NAME', 'my-domain'),
    'aws_opensearch_collection_id': ('AWS_OPENSEARCH_COLLECTION_ID', 'col-123'),
}

# Int-typed fields and a representative env value -> expected coerced result.
INT_FIELD_TO_ENV = {
    'opensearch_timeout': ('OPENSEARCH_TIMEOUT', '45', 45),
    'opensearch_max_response_size': ('OPENSEARCH_MAX_RESPONSE_SIZE', '5242880', 5242880),
    'opensearch_memory_monitor_interval': ('OPENSEARCH_MEMORY_MONITOR_INTERVAL', '120', 120),
}

# Bool flags that currently parse via ``== 'true'`` -> shared union parser.
TRUTHY_FLAG_FIELDS = {
    'opensearch_no_auth': 'OPENSEARCH_NO_AUTH',
    'aws_opensearch_serverless': 'AWS_OPENSEARCH_SERVERLESS',
    'opensearch_header_auth': 'OPENSEARCH_HEADER_AUTH',
    'memory_tools_enabled': 'MEMORY_TOOLS_ENABLED',
    'opensearch_settings_allow_write': 'OPENSEARCH_SETTINGS_ALLOW_WRITE',
}


@pytest.fixture
def clean_env(monkeypatch):
    """Remove every modeled env var so each test starts from a known-empty environment."""
    aliases = set()
    for _, alias in TRUTHY_FLAG_FIELDS.items():
        aliases.add(alias)
    for _, (alias, _) in FIELD_TO_ENV.items():
        aliases.add(alias)
    for _, (alias, _, _) in INT_FIELD_TO_ENV.items():
        aliases.add(alias)
    aliases.add('OPENSEARCH_SSL_VERIFY')
    for alias in aliases:
        monkeypatch.delenv(alias, raising=False)
    return monkeypatch


def test_defaults_match_current_behavior(clean_env):
    """With no env set, every field equals the documented current default."""
    settings = Settings()
    for field, expected in EXPECTED_DEFAULTS.items():
        assert getattr(settings, field) == expected, field


def test_default_dict_covers_every_field(clean_env):
    """The defaults map must enumerate exactly the model's fields (no field missed)."""
    assert set(EXPECTED_DEFAULTS) == set(Settings.model_fields)


@pytest.mark.parametrize('field,alias_value', sorted(FIELD_TO_ENV.items()))
def test_string_field_reads_from_alias(clean_env, field, alias_value):
    """Each string field reads its value from the exact current env-var alias."""
    alias, value = alias_value
    clean_env.setenv(alias, value)
    settings = Settings()
    assert getattr(settings, field) == value


@pytest.mark.parametrize('field,alias_value', sorted(INT_FIELD_TO_ENV.items()))
def test_int_field_reads_from_alias(clean_env, field, alias_value):
    """Each int field reads and coerces its value from the exact current env-var alias."""
    alias, raw, expected = alias_value
    clean_env.setenv(alias, raw)
    settings = Settings()
    assert getattr(settings, field) == expected


@pytest.mark.parametrize('field,alias', sorted(TRUTHY_FLAG_FIELDS.items()))
def test_truthy_flag_true_spellings(clean_env, field, alias):
    """Only ``true`` (any case, trimmed) parses to True — matches live ``== 'true'``."""
    for spelling in ('true', 'TRUE', 'True', '  true  '):
        clean_env.setenv(alias, spelling)
        assert getattr(Settings(), field) is True, (field, spelling)


@pytest.mark.parametrize('field,alias', sorted(TRUTHY_FLAG_FIELDS.items()))
def test_truthy_flag_false_spellings(clean_env, field, alias):
    """Everything other than ``"true"`` is False — including ``1``/``yes``.

    This is the regression guard for the adversarial finding: widening the truthy
    set to include ``"1"``/``"yes"`` would let a typo'd ``OPENSEARCH_NO_AUTH=1``
    silently disable authentication. These flags must be EXACTLY ``lower()=='true'``.
    """
    for spelling in ('false', 'FALSE', '0', 'no', 'off', '', '1', 'yes', 'YES'):
        clean_env.setenv(alias, spelling)
        assert getattr(Settings(), field) is False, (field, spelling)


def test_parse_bool_string_truthy():
    """parse_bool_string accepts only the case-insensitive string 'true' (trimmed)."""
    for value in ('true', 'TRUE', 'True', '  true  '):
        assert parse_bool_string(value) is True, value


def test_parse_bool_string_falsy():
    """parse_bool_string rejects everything other than 'true' — incl. '1'/'yes'."""
    for value in ('false', 'FALSE', '0', 'no', 'off', '', '2', 'enabled', '1', 'yes', 'YES'):
        assert parse_bool_string(value) is False, value


def test_parse_bool_string_passthrough_bool():
    """A real bool is returned unchanged."""
    assert parse_bool_string(True) is True
    assert parse_bool_string(False) is False


def test_ssl_verify_true_unless_false(clean_env):
    """OPENSEARCH_SSL_VERIFY is True by default and disabled only by explicit 'false'."""
    # Unset -> default True
    assert Settings().opensearch_ssl_verify is True

    # Explicit 'false' (any case) -> False
    for spelling in ('false', 'FALSE', 'False', '  false  '):
        clean_env.setenv('OPENSEARCH_SSL_VERIFY', spelling)
        assert Settings().opensearch_ssl_verify is False, spelling

    # Anything else stays True (matches current `!= 'false'` semantic exactly)
    for spelling in ('true', '1', '0', 'no', 'yes', 'anything'):
        clean_env.setenv('OPENSEARCH_SSL_VERIFY', spelling)
        assert Settings().opensearch_ssl_verify is True, spelling


def test_parse_ssl_verify_helper():
    """parse_ssl_verify returns False only for case-insensitive 'false'."""
    assert parse_ssl_verify('false') is False
    assert parse_ssl_verify('FALSE') is False
    assert parse_ssl_verify('true') is True
    assert parse_ssl_verify('0') is True
    assert parse_ssl_verify('') is True
    assert parse_ssl_verify(False) is False


def test_unknown_env_var_does_not_crash(clean_env):
    """An unknown extra env var is ignored (BaseSettings extra='ignore' default)."""
    clean_env.setenv('SOME_TOTALLY_UNRELATED_ENV_VAR', 'whatever')
    clean_env.setenv('OPENSEARCH_NOT_A_REAL_SETTING', 'value')
    settings = Settings()  # must not raise
    assert settings.opensearch_url == ''
    assert not hasattr(settings, 'some_totally_unrelated_env_var')


def test_allow_write_default_true_when_unset(clean_env):
    """OPENSEARCH_SETTINGS_ALLOW_WRITE defaults to True when unset (current behavior)."""
    assert Settings().opensearch_settings_allow_write is True


def test_dynamic_connection_kept_raw(clean_env):
    """OPENSEARCH_DYNAMIC_CONNECTION is a raw string so caller keeps tri-state logic."""
    clean_env.setenv('OPENSEARCH_DYNAMIC_CONNECTION', '0')
    assert Settings().opensearch_dynamic_connection == '0'
    clean_env.setenv('OPENSEARCH_DYNAMIC_CONNECTION', 'true')
    assert Settings().opensearch_dynamic_connection == 'true'


def test_password_preserves_whitespace(clean_env):
    """The password field is stored verbatim (the model does not strip)."""
    clean_env.setenv('OPENSEARCH_PASSWORD', '  pad ded  ')
    assert Settings().opensearch_password == '  pad ded  '


# --- int-field parsing fidelity (matches client.py call-site behavior exactly) ---


def test_max_response_size_zero_falls_back_to_none(clean_env):
    """OPENSEARCH_MAX_RESPONSE_SIZE <= 0 clamps to None (client.py warns + uses default)."""
    clean_env.setenv('OPENSEARCH_MAX_RESPONSE_SIZE', '0')
    assert Settings().opensearch_max_response_size is None
    clean_env.setenv('OPENSEARCH_MAX_RESPONSE_SIZE', '-100')
    assert Settings().opensearch_max_response_size is None


def test_max_response_size_invalid_falls_back_to_none(clean_env):
    """A non-integer OPENSEARCH_MAX_RESPONSE_SIZE degrades to None (never raises)."""
    clean_env.setenv('OPENSEARCH_MAX_RESPONSE_SIZE', 'not-a-number')
    assert Settings().opensearch_max_response_size is None


def test_max_response_size_positive_kept(clean_env):
    """A valid positive OPENSEARCH_MAX_RESPONSE_SIZE is preserved."""
    clean_env.setenv('OPENSEARCH_MAX_RESPONSE_SIZE', '5242880')
    assert Settings().opensearch_max_response_size == 5242880


def test_timeout_empty_is_none(clean_env):
    """An unset/empty OPENSEARCH_TIMEOUT yields None."""
    assert Settings().opensearch_timeout is None


def test_timeout_invalid_raises(clean_env):
    """A non-integer OPENSEARCH_TIMEOUT raises, matching client.py's int(x) with no guard."""
    import pytest
    from pydantic import ValidationError

    clean_env.setenv('OPENSEARCH_TIMEOUT', 'abc')
    with pytest.raises((ValueError, ValidationError)):
        Settings()

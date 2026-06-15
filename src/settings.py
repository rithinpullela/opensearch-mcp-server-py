# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed, single-source-of-truth settings model for the OpenSearch MCP Server.

This module introduces a ``pydantic-settings`` ``Settings`` model that enumerates
**every** environment variable the server reads today, exactly once, with the current
env-var name as the field alias, the current type, and the current default value.

It is introduced **unwired**: no existing module imports it yet. Call sites are migrated
in a later phase (see ``DESIGN_DECISIONS.md`` section 5). Because the aliases reproduce
today's env-var names exactly, the public configuration surface is unchanged.

Environment variables modeled (alias -> field):

Connection / single-mode auth (``src/opensearch/client.py``):
    - ``OPENSEARCH_URL``                  -> opensearch_url            (str, default '')
    - ``OPENSEARCH_USERNAME``             -> opensearch_username       (str, default '')
    - ``OPENSEARCH_PASSWORD``             -> opensearch_password       (str, default '')
    - ``OPENSEARCH_NO_AUTH``              -> opensearch_no_auth        (bool, default False)
    - ``AWS_IAM_ARN``                     -> aws_iam_arn               (str, default '')
    - ``AWS_PROFILE``                     -> aws_profile               (str, default '')
    - ``AWS_REGION``                      -> aws_region                (str, default '')
    - ``AWS_OPENSEARCH_SERVERLESS``       -> aws_opensearch_serverless (bool, default False)
    - ``OPENSEARCH_HEADER_AUTH``          -> opensearch_header_auth    (bool, default False)
    - ``OPENSEARCH_TIMEOUT``              -> opensearch_timeout        (Optional[int], default None)
    - ``OPENSEARCH_SSL_VERIFY``           -> opensearch_ssl_verify     (bool, default True)
    - ``OPENSEARCH_CA_CERT_PATH``         -> opensearch_ca_cert_path   (str, default '')
    - ``OPENSEARCH_CLIENT_CERT_PATH``     -> opensearch_client_cert_path (str, default '')
    - ``OPENSEARCH_CLIENT_KEY_PATH``      -> opensearch_client_key_path  (str, default '')
    - ``OPENSEARCH_MAX_RESPONSE_SIZE``    -> opensearch_max_response_size (Optional[int], default None)

Query behavior (``src/opensearch/helper.py``):
    - ``OPENSEARCH_QUERY_TIMEOUT``        -> opensearch_query_timeout  (str, default '')

Dynamic connection / server instructions (``src/mcp_server_opensearch/server_instructions.py``):
    - ``OPENSEARCH_DYNAMIC_CONNECTION``   -> opensearch_dynamic_connection (str, default '')

Tool filtering (``src/tools/tool_filter.py``):
    - ``OPENSEARCH_ENABLED_TOOLS``                  -> opensearch_enabled_tools           (str, default '')
    - ``OPENSEARCH_DISABLED_TOOLS``                 -> opensearch_disabled_tools          (str, default '')
    - ``OPENSEARCH_TOOL_CATEGORIES``                -> opensearch_tool_categories         (str, default '')
    - ``OPENSEARCH_ENABLED_CATEGORIES``             -> opensearch_enabled_categories      (str, default '')
    - ``OPENSEARCH_DISABLED_CATEGORIES``            -> opensearch_disabled_categories     (str, default '')
    - ``OPENSEARCH_ENABLED_TOOLS_REGEX``            -> opensearch_enabled_tools_regex     (str, default '')
    - ``OPENSEARCH_DISABLED_TOOLS_REGEX``           -> opensearch_disabled_tools_regex    (str, default '')
    - ``OPENSEARCH_SETTINGS_ALLOW_WRITE``           -> opensearch_settings_allow_write    (bool, default True)
    - ``OPENSEARCH_SETTINGS_ALLOW_WRITE_CATEGORIES``-> opensearch_settings_allow_write_categories (str, default '')

Agentic memory (``src/tools/memory_tools.py``, ``src/tools/config.py``):
    - ``MEMORY_TOOLS_ENABLED``            -> memory_tools_enabled      (bool, default False)
    - ``MEMORY_INDEX_NAME``              -> memory_index_name         (str, default 'agent-memory')
    - ``MEMORY_USER_ID``                  -> memory_user_id            (str, default '')
    - ``MEMORY_AGENT_ID``                 -> memory_agent_id           (str, default '')
    - ``OPENSEARCH_MEMORY_CONTAINER_ID``  -> opensearch_memory_container_id (str, default '')
    - ``AWS_OPENSEARCH_DOMAIN_NAME``      -> aws_opensearch_domain_name (str, default '')
    - ``AWS_OPENSEARCH_COLLECTION_ID``    -> aws_opensearch_collection_id (str, default '')

Logging / monitoring (``src/mcp_server_opensearch/logging_config.py``):
    - ``OPENSEARCH_MEMORY_MONITOR_INTERVAL`` -> opensearch_memory_monitor_interval (int, default 60)

Truthy-parsing notes (preserved exactly so migration flips no flag):
    The shared ``parse_bool_string`` validator accepts the **union** of every truthy
    spelling observed in the current codebase: ``true`` / ``1`` / ``yes`` (case-insensitive,
    surrounding whitespace stripped). Anything else is False.

    Per-variable, today's code parses as follows; the union parser is a strict superset
    so no current input changes meaning:
    - ``OPENSEARCH_NO_AUTH``, ``AWS_OPENSEARCH_SERVERLESS``, ``OPENSEARCH_HEADER_AUTH``,
      ``MEMORY_TOOLS_ENABLED``: ``value.lower() == 'true'`` (only ``"true"`` is truthy today).
    - ``OPENSEARCH_SETTINGS_ALLOW_WRITE``: ``value.lower() == 'true'`` but **defaults to True**
      (``os.getenv(..., 'true')``), so an unset or any non-``"true"`` value other than the
      default yields False; the default-when-unset is True.
    - ``OPENSEARCH_SSL_VERIFY``: ``value.lower() != 'false'`` with default ``'true'`` — i.e.
      True unless explicitly ``"false"``. This is an *inverted* spelling (only ``"false"`` is
      falsy). It is modeled as a plain bool with a dedicated validator that preserves this
      "True unless 'false'" semantic exactly; the shared union parser is NOT used for it.
    - ``OPENSEARCH_DYNAMIC_CONNECTION``: tri-state — ``"true"``/``"1"`` on, ``"false"``/``"0"``
      off, unset/empty auto-detect. Kept as a raw ``str`` field (default '') so the existing
      tri-state logic in ``server_instructions.py`` is reproduced verbatim by the caller.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


# Default memory index name; mirrors ``DEFAULT_MEMORY_INDEX_NAME`` in
# ``src/tools/memory_tools.py`` so the unset behavior matches exactly.
DEFAULT_MEMORY_INDEX_NAME = 'agent-memory'

# The union of every truthy spelling observed across the current codebase.
# Used by ``parse_bool_string``; documented per-variable in the module docstring.
_TRUTHY_VALUES = frozenset({'true', '1', 'yes'})


def parse_bool_string(value: object) -> bool:
    """Parse a truthy string using the union of all current spellings.

    Accepts ``true`` / ``1`` / ``yes`` case-insensitively (with surrounding whitespace
    stripped). Any other string is False. Non-string values are coerced via ``bool``.

    This is the shared parser for every flag whose current code is
    ``value.lower() == 'true'``; the accepted set is a strict superset of ``"true"``,
    so no input that is truthy today becomes falsy (and vice versa).

    Args:
        value: The raw value to parse (typically a ``str`` from the environment).

    Returns:
        bool: True when ``value`` is one of the accepted truthy spellings.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_VALUES
    return bool(value)


def parse_max_response_size(value: object) -> Optional[int]:
    """Parse ``OPENSEARCH_MAX_RESPONSE_SIZE`` exactly as ``client.py`` does today.

    Reproduces the current graceful behavior (``client.py`` ~lines 243-256): an empty
    value is ``None``; a valid positive int is used as-is; a value ``<= 0`` or a
    non-integer string falls back to ``None`` (the current code logs a warning and
    uses the default). **It never raises** — a bad value degrades to ``None``.

    Args:
        value: The raw value (typically a ``str`` from the environment).

    Returns:
        Optional[int]: A positive int, or ``None`` for empty/invalid/``<= 0`` input.
    """
    if value is None:
        return None
    if isinstance(value, int):
        # Match the runtime clamp: any value <= 0 falls back to None.
        return value if value > 0 else None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = int(stripped)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def parse_optional_int(value: object) -> Optional[int]:
    """Parse ``OPENSEARCH_TIMEOUT`` exactly as ``client.py`` does today.

    Reproduces ``int(x.strip()) if x else None`` (``client.py`` ~line 235-236): empty
    is ``None``; otherwise ``int()`` is applied directly. Unlike
    :func:`parse_max_response_size`, the current code has **no** try/except here, so a
    non-numeric value raises ``ValueError`` — that behavior is preserved faithfully.

    Args:
        value: The raw value (typically a ``str`` from the environment).

    Returns:
        Optional[int]: The parsed int, or ``None`` for empty input.

    Raises:
        ValueError: If a non-empty value is not a valid integer (matches today).
    """
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        return int(stripped) if stripped else None
    return None


def parse_ssl_verify(value: object) -> bool:
    """Parse the ``OPENSEARCH_SSL_VERIFY`` flag (True unless explicitly ``"false"``).

    Reproduces the current semantic ``os.getenv('OPENSEARCH_SSL_VERIFY', 'true').lower()
    != 'false'`` exactly: verification is enabled by default and disabled **only** when the
    value is case-insensitively ``"false"``. Any other value (including ``"0"`` or ``"no"``)
    leaves verification enabled.

    Args:
        value: The raw value to parse (typically a ``str`` from the environment).

    Returns:
        bool: False only when ``value`` is case-insensitively ``"false"``; True otherwise.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() != 'false'
    return bool(value)


class Settings(BaseSettings):
    """Typed settings model enumerating every environment variable the server reads.

    Each field uses the exact current env-var name as its alias, the current type, and the
    current default value, so reading from the environment reproduces today's behavior. The
    model is case-insensitive on env-var names and ignores unknown environment variables
    (``extra='ignore'``), matching ``BaseSettings`` defaults.

    See the module docstring for the full env-var -> field mapping and truthy-parsing notes.
    """

    model_config = SettingsConfigDict(
        populate_by_name=True,
        case_sensitive=False,
        extra='ignore',
    )

    # --- Connection / single-mode auth (src/opensearch/client.py) ---
    opensearch_url: str = ''
    opensearch_username: str = ''
    opensearch_password: str = ''
    opensearch_no_auth: bool = False
    aws_iam_arn: str = ''
    aws_profile: str = ''
    aws_region: str = ''
    aws_opensearch_serverless: bool = False
    opensearch_header_auth: bool = False
    opensearch_timeout: Optional[int] = None
    opensearch_ssl_verify: bool = True
    opensearch_ca_cert_path: str = ''
    opensearch_client_cert_path: str = ''
    opensearch_client_key_path: str = ''
    opensearch_max_response_size: Optional[int] = None

    # --- Query behavior (src/opensearch/helper.py) ---
    opensearch_query_timeout: str = ''

    # --- Dynamic connection (src/mcp_server_opensearch/server_instructions.py) ---
    # Kept raw so the tri-state logic (true/1 on, false/0 off, empty auto) stays with caller.
    opensearch_dynamic_connection: str = ''

    # --- Tool filtering (src/tools/tool_filter.py) ---
    opensearch_enabled_tools: str = ''
    opensearch_disabled_tools: str = ''
    opensearch_tool_categories: str = ''
    opensearch_enabled_categories: str = ''
    opensearch_disabled_categories: str = ''
    opensearch_enabled_tools_regex: str = ''
    opensearch_disabled_tools_regex: str = ''
    opensearch_settings_allow_write: bool = True
    opensearch_settings_allow_write_categories: str = ''

    # --- Agentic memory (src/tools/memory_tools.py, src/tools/config.py) ---
    memory_tools_enabled: bool = False
    memory_index_name: str = DEFAULT_MEMORY_INDEX_NAME
    memory_user_id: str = ''
    memory_agent_id: str = ''
    opensearch_memory_container_id: str = ''
    aws_opensearch_domain_name: str = ''
    aws_opensearch_collection_id: str = ''

    # --- Logging / monitoring (src/mcp_server_opensearch/logging_config.py) ---
    opensearch_memory_monitor_interval: int = 60

    @field_validator(
        'opensearch_no_auth',
        'aws_opensearch_serverless',
        'opensearch_header_auth',
        'memory_tools_enabled',
        'opensearch_settings_allow_write',
        mode='before',
    )
    @classmethod
    def _validate_truthy_flags(cls, value: object) -> bool:
        """Parse the standard ``== 'true'`` flags with the shared union parser."""
        return parse_bool_string(value)

    @field_validator('opensearch_ssl_verify', mode='before')
    @classmethod
    def _validate_ssl_verify(cls, value: object) -> bool:
        """Parse ``OPENSEARCH_SSL_VERIFY`` with its inverted (True-unless-'false') semantic."""
        return parse_ssl_verify(value)

    @field_validator('opensearch_max_response_size', mode='before')
    @classmethod
    def _validate_max_response_size(cls, value: object) -> Optional[int]:
        """Parse ``OPENSEARCH_MAX_RESPONSE_SIZE`` with the graceful <=0/invalid -> None clamp."""
        return parse_max_response_size(value)

    @field_validator('opensearch_timeout', mode='before')
    @classmethod
    def _validate_timeout(cls, value: object) -> Optional[int]:
        """Parse ``OPENSEARCH_TIMEOUT`` as ``int(x) if x else None`` (raises on bad input, as today)."""
        return parse_optional_int(value)

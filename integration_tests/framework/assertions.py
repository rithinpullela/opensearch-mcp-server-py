# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json


def _extract_texts(result) -> str:
    """Extract text content from an MCP tool call result."""
    texts = [item.text for item in result.content if hasattr(item, 'text')]
    return '\n'.join(texts)


_ERROR_PREFIXES = ('Error', 'Input validation error')


def assert_tool_success(result, *expected: str) -> str:
    """Assert that an MCP tool call returned a non-error response.

    Primary signal is the protocol flag ``result.isError`` (must not be True); the
    legacy ``Error``-prefix text check is kept as a secondary belt-and-suspenders so
    a regression in either the flag or the text is caught.

    Args:
        result: The MCP tool call result.
        *expected: One or more substrings that must appear in the response.

    Returns:
        The concatenated text content from the response.
    """
    text = _extract_texts(result)
    assert getattr(result, 'isError', None) is not True, (
        f'Tool returned isError=True: {text[:500]}'
    )
    assert not text.startswith(_ERROR_PREFIXES), f'Tool returned error text: {text[:500]}'
    for exp in expected:
        assert exp in text, f'Expected "{exp}" not found in response: {text[:500]}'
    return text


def assert_tool_error(result, expected_substring: str | None = None) -> str:
    """Assert that an MCP tool call returned an error.

    Primary signal is the protocol flag ``result.isError`` (must be True), per the MCP
    spec for tool-execution failures. The error text is still formatted by the server's
    ``log_tool_error()`` as ``"Error <operation>: <exception>"`` / ``"Error: <exception>"``
    and that prefix is asserted as a secondary check.

    Args:
        result: The MCP tool call result.
        expected_substring: If provided, assert this substring appears in the error text
                            (case-insensitive).

    Returns:
        The concatenated text content from the error response.
    """
    text = _extract_texts(result)
    assert getattr(result, 'isError', None) is True, (
        f'Expected isError=True but got success: {text[:500]}'
    )
    assert text.startswith(_ERROR_PREFIXES), f'Expected error text but got: {text[:500]}'
    if expected_substring:
        assert expected_substring.lower() in text.lower(), (
            f"Expected '{expected_substring}' in error response: {text[:500]}"
        )
    return text


def assert_contains_json(result, *expected_keys: str) -> dict | list:
    """Assert the response contains parseable JSON and return it.

    Args:
        result: The MCP tool call result.
        *expected_keys: Top-level keys that must exist in the parsed JSON dict.

    Tries to extract JSON from the text content. Handles cases where the
    JSON is preceded by a description line.
    """
    text = assert_tool_success(result)
    parsed = None

    # Try parsing the whole text first
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try finding JSON starting from first { or [
    if parsed is None:
        for start_char in ['{', '[']:
            idx = text.find(start_char)
            if idx >= 0:
                try:
                    parsed = json.loads(text[idx:])
                    break
                except json.JSONDecodeError:
                    continue

    if parsed is None:
        raise AssertionError(f'No parseable JSON found in response: {text[:500]}')

    if expected_keys and isinstance(parsed, dict):
        for key in expected_keys:
            assert key in parsed, f'Expected key "{key}" not in JSON: {list(parsed.keys())}'

    return parsed

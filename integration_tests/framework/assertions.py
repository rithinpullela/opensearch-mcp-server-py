# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json


def _extract_texts(result) -> str:
    """Extract text content from an MCP tool call result."""
    texts = [item.text for item in result.content if hasattr(item, 'text')]
    return '\n'.join(texts)


def _has_error_flag(result) -> bool:
    """Check if any content item has is_error=True, or the top-level isError is set."""
    if getattr(result, 'isError', False):
        return True
    return any(getattr(item, 'is_error', False) for item in result.content)


def assert_tool_success(result) -> str:
    """Assert that an MCP tool call returned a non-error response.

    Returns:
        The concatenated text content from the response.
    """
    text = _extract_texts(result)
    assert not _has_error_flag(result), f'Tool returned error: {text[:500]}'
    return text


def assert_tool_error(result, expected_substring: str | None = None) -> str:
    """Assert that an MCP tool call returned an error.

    Args:
        result: The MCP tool call result.
        expected_substring: If provided, assert this substring appears in the error text
                            (case-insensitive).

    Returns:
        The concatenated text content from the error response.
    """
    text = _extract_texts(result)
    assert _has_error_flag(result), f'Expected error but got success: {text[:500]}'
    if expected_substring:
        assert expected_substring.lower() in text.lower(), (
            f"Expected '{expected_substring}' in error response: {text[:500]}"
        )
    return text


def assert_contains_json(result) -> dict | list:
    """Assert the response contains parseable JSON and return it.

    Tries to extract JSON from the text content. Handles cases where the
    JSON is preceded by a description line.
    """
    text = assert_tool_success(result)
    # Try parsing the whole text first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try finding JSON starting from first { or [
    for start_char in ['{', '[']:
        idx = text.find(start_char)
        if idx >= 0:
            try:
                return json.loads(text[idx:])
            except json.JSONDecodeError:
                continue

    raise AssertionError(f'No parseable JSON found in response: {text[:500]}')

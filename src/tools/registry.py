# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed tool registry for the OpenSearch MCP Server.

This is the leaf module that defines the *shape* of a tool entry (``ToolSpec``)
and an insertion-ordered ``ToolRegistry`` that domain modules register into.

Why this exists
---------------
The legacy ``tools.TOOL_REGISTRY`` is a single 344-line dict literal assembled by
``**``-spreading several sub-registries. That made the tool catalog hard to read,
hard to extend (every new tool edits one giant file), and silently tolerant of
key collisions and missing keys. ``ToolRegistry`` keeps the exact same *runtime
shape* — a plain ``dict[str, ToolSpec]`` keyed by canonical tool name — so every
existing consumer (``tool_filter``, ``tool_executor``, ``config``) keeps working
unchanged, while adding:

* a documented, type-checked ``ToolSpec`` (no more guessing which keys exist),
* **fail-loud duplicate-key detection** (the legacy ``**`` spread was
  last-writer-wins and silently masked collisions), and
* insertion-order preservation, so the composed catalog order is deterministic
  and pinnable by a test.

``ToolSpec`` is a ``TypedDict`` on purpose: entries remain ordinary dicts, so code
that does ``spec['function']`` / ``spec.get('min_version')`` is unaffected.
"""

from typing import Any, Callable, TypedDict
from typing_extensions import NotRequired


class ToolSpec(TypedDict):
    """The shape of a single tool entry in the registry.

    Required keys are present on every tool; the rest are optional flags/metadata
    consumed by the version gate, the write-protection filter, and per-mode schema
    mutation. Keys mirror the legacy registry exactly — do not rename them.
    """

    # --- required on every tool ---
    display_name: str
    description: str
    input_schema: dict[str, Any]
    function: Callable[..., Any]
    args_model: type
    # comma-joined HTTP method string, e.g. ``'GET'`` or ``'GET, POST'``.
    # The write-protection filter substring-matches ``'GET'`` against this.
    http_methods: str

    # --- optional metadata / flags ---
    # Version gating. ``None``/absent => always compatible (see is_tool_compatible).
    min_version: NotRequired[str]
    max_version: NotRequired[str]
    # Only registered/visible in multi-cluster mode (e.g. ListClustersTool).
    multi_only: NotRequired[bool]
    # Exempt from the list-time write-protection filter (e.g. memory save/delete).
    bypass_write_filter: NotRequired[bool]
    # Marks a memory tool; excluded from multi-mode schema views.
    memory_tool: NotRequired[bool]
    # Per-tool response clamp, injectable via YAML config (e.g. SearchIndexTool).
    max_size_limit: NotRequired[int]


# Keys that must be present on every registered tool.
_REQUIRED_KEYS = ('display_name', 'description', 'input_schema', 'function', 'args_model')


class DuplicateToolError(ValueError):
    """Raised when two tools register under the same canonical key.

    The legacy ``**``-spread registry silently let a later entry overwrite an
    earlier one. Surfacing it as a hard error prevents a whole class of
    accidental-shadowing bugs as the catalog is split across domain modules.
    """


class ToolRegistry:
    """Insertion-ordered registry of tool specs, keyed by canonical tool name.

    Behaves like the legacy ``dict[str, ToolSpec]`` for all read access
    (``registry[key]``, ``in``, ``.items()``, ``.keys()``, ``.values()``,
    ``len()``, iteration), so it is a drop-in for consumers that expect a dict.
    Writes go through :meth:`add`, which validates and rejects duplicates.
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._tools: dict[str, ToolSpec] = {}

    def add(self, name: str, spec: ToolSpec) -> None:
        """Register ``spec`` under canonical key ``name``.

        Args:
            name: The canonical registry key (e.g. ``'ListIndexTool'``).
            spec: The tool spec; must contain the required keys.

        Raises:
            DuplicateToolError: If ``name`` is already registered.
            ValueError: If ``spec`` is missing a required key.
        """
        if name in self._tools:
            raise DuplicateToolError(f'Tool already registered under key: {name!r}')
        missing = [k for k in _REQUIRED_KEYS if k not in spec]
        if missing:
            raise ValueError(f'Tool {name!r} is missing required key(s): {missing}')
        self._tools[name] = spec

    def update(self, entries: dict[str, ToolSpec]) -> None:
        """Bulk-register ``entries`` (in iteration order), validating each.

        Convenience for adopting an existing ``dict``-shaped sub-registry while
        still getting duplicate detection. Equivalent to calling :meth:`add` for
        each item.
        """
        for name, spec in entries.items():
            self.add(name, spec)

    def as_dict(self) -> dict[str, ToolSpec]:
        """Return a shallow copy as a plain ``dict`` (insertion order preserved).

        Use this when handing the catalog to code that mutates or deep-copies the
        registry (e.g. ``apply_custom_tool_config``), so the registry's own store
        is never mutated as a side effect.
        """
        return dict(self._tools)

    # --- dict-compatible read API (so this is a drop-in for the legacy dict) ---

    def __getitem__(self, key: str) -> ToolSpec:
        """Return the spec registered under ``key`` (raises ``KeyError`` if absent)."""
        return self._tools[key]

    def __contains__(self, key: object) -> bool:
        """Return whether a tool is registered under ``key``."""
        return key in self._tools

    def __iter__(self):
        """Iterate canonical tool keys in registration order."""
        return iter(self._tools)

    def __len__(self) -> int:
        """Return the number of registered tools."""
        return len(self._tools)

    def keys(self):
        """Return a view of canonical tool keys in registration order."""
        return self._tools.keys()

    def values(self):
        """Return a view of tool specs in registration order."""
        return self._tools.values()

    def items(self):
        """Return a view of ``(key, spec)`` pairs in registration order."""
        return self._tools.items()

    def get(self, key: str, default: Any = None) -> Any:
        """Return the spec for ``key``, or ``default`` if not registered."""
        return self._tools.get(key, default)

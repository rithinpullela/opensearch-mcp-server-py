# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable per-server runtime context.

Replaces the scattered process-global mutable state in ``global_state.py``
(``_current_mode`` / ``_current_profile`` / ``_current_config_file_path`` set at
boot and read implicitly throughout the call graph) with a single immutable value
object that is built once during bootstrap and threaded explicitly.

Why
---
Module-global ``set_mode``/``get_mode`` has two problems the audit flagged
(P1-20, P2-10): the boot order is load-bearing but invisible (mode *must* be set
before any tool registration or per-mode schema views compute wrong), and
``get_mode()`` silently defaults to ``'single'`` when unset, masking that
ordering bug. An immutable ``ServerContext`` makes the dependency explicit, is
trivially testable (construct one, pass it in), and is safe to share across the
concurrent requests of the stateless Streamable HTTP server because it is never
mutated after construction.

This is introduced additively. The existing ``global_state`` functions remain the
source of truth until each subsystem is migrated to read from a threaded
``ServerContext`` in later phases; at that point ``global_state`` becomes a thin
compatibility shim. Keeping both in lockstep here changes no behavior.
"""

from dataclasses import dataclass
from typing import Literal


Mode = Literal['single', 'multi']


@dataclass(frozen=True, slots=True)
class ServerContext:
    """Immutable snapshot of the server's runtime configuration.

    Built once by the bootstrap step from parsed CLI args / settings and passed
    explicitly to the registry builder, the serve pipeline, and (eventually) the
    tool layer, replacing implicit reads of ``global_state``.

    Attributes:
        mode: Server mode — ``'single'`` (env/per-call connection) or ``'multi'``
            (per-cluster config). Mirrors ``global_state.get_mode()``.
        profile: AWS profile name, or ``''`` if unset. Mirrors ``get_profile()``.
        config_file_path: Path to the YAML config file, or ``''`` if none.
            Mirrors ``get_config_file_path()``.
    """

    mode: Mode = 'single'
    profile: str = ''
    config_file_path: str = ''

    @property
    def is_multi(self) -> bool:
        """Return whether the server is running in multi-cluster mode."""
        return self.mode == 'multi'

    @property
    def has_config_file(self) -> bool:
        """Return whether a YAML config file path was provided."""
        return bool(self.config_file_path)

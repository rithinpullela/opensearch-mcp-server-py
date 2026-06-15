# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Pydantic argument models for the 4 static (ex-generated) tools.

These models are used for **runtime argument validation** (``validate_args_for_mode``)
only — they are NOT the source of the advertised ``input_schema`` (that is hand-built
in ``schema.py`` to byte-match the legacy generator). The generator likewise validated
against a permissive ``create_model`` whose non-base fields were all ``str`` with no
default; we mirror that with ``Optional[str]`` / ``Optional[Any]`` so the same inputs
validate the same way.

The ``body`` field is ``Optional[Any]`` (the generator typed body as ``Any``); path/
query parameters are ``Optional[str]``. ``index``/``id`` requiredness is enforced by
the advertised schema's ``required`` list (and the endpoint selection), matching the
generator, which did not make them required on the Pydantic model itself.
"""

from tools.tool_params import baseToolArgs
from typing import Any, Optional


class MsearchArgs(baseToolArgs):
    """Arguments for MsearchTool (``_msearch``)."""

    index: Optional[str] = None
    body: Optional[Any] = None


class ExplainArgs(baseToolArgs):
    """Arguments for ExplainTool (``{index}/_explain/{id}``)."""

    index: Optional[str] = None
    id: Optional[str] = None
    body: Optional[Any] = None


class CountArgs(baseToolArgs):
    """Arguments for CountTool (``_count``)."""

    index: Optional[str] = None
    body: Optional[Any] = None


class ClusterHealthArgs(baseToolArgs):
    """Arguments for ClusterHealthTool (``_cluster/health``)."""

    index: Optional[str] = None

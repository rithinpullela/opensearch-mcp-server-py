# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Pydantic argument models for the 4 static (ex-generated) tools.

These models are used for **runtime argument validation** (``validate_args_for_mode``)
only — they are NOT the source of the advertised ``input_schema`` (that is hand-built
in ``schema.py`` to byte-match the legacy generator).

Fidelity note — TOOL-SPECIFIC args match the old generator exactly; BASE args are
intentionally stricter (see DECISION_LOG D15):

* Tool-specific params: the generator built these via
  ``create_model(..., index=(str, None))`` for path/query params and ``(Any, None)``
  for the body. Under pydantic v2 a field typed ``(str, None)`` is required-typed with
  default ``None`` — it accepts omission and a string but **rejects an explicit
  ``null``**; ``(Any, None)`` accepts ``null``. We reproduce that exactly here
  (``index``/``id`` → ``(str, None)``; ``body`` → ``(Any, None)``). A naive
  ``Optional[str] = None`` would have loosened it.

* Base connection args (the 11 ``baseToolArgs`` fields): the old generator coerced
  EVERY base field to ``str`` (``str`` for all, ``Any`` only for body). We instead
  inherit ``baseToolArgs``' real types (``aws_opensearch_serverless: bool``,
  ``opensearch_timeout: int``, etc.) via ``__base__=baseToolArgs``. This is a
  deliberate, observable change (DECISION_LOG D15 / O-list): the 4 ex-generated tools
  now validate base args with their true types instead of accepting only strings —
  the same typed validation every other tool already uses. Pinned by
  ``tests/tools/domains/test_generated_params.py``.
"""

from pydantic import create_model
from tools.tool_params import baseToolArgs
from typing import Any


# index/id: typed str with default None -> reject explicit null, allow omission/value.
# body: typed Any with default None -> allow null (matches the generator).
MsearchArgs = create_model(
    'MsearchArgs', __base__=baseToolArgs, index=(str, None), body=(Any, None)
)
ExplainArgs = create_model(
    'ExplainArgs', __base__=baseToolArgs, index=(str, None), id=(str, None), body=(Any, None)
)
CountArgs = create_model('CountArgs', __base__=baseToolArgs, index=(str, None), body=(Any, None))
ClusterHealthArgs = create_model('ClusterHealthArgs', __base__=baseToolArgs, index=(str, None))

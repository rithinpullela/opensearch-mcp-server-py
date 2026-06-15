# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Pydantic argument models for the 4 static (ex-generated) tools.

These models are used for **runtime argument validation** (``validate_args_for_mode``)
only — they are NOT the source of the advertised ``input_schema`` (that is hand-built
in ``schema.py`` to byte-match the legacy generator).

Fidelity note (validation must match the old generator EXACTLY): the generator built
these via ``create_model(f'{base}Args', __base__=baseToolArgs, **{name: (str, None)})``
for path/query params and ``(Any, None)`` for the body. Under pydantic v2 a field typed
``(str, None)`` is a *required-typed* field with default ``None`` — it accepts omission
(uses ``None``) and a string, but **rejects an explicit ``null``** with a ValidationError.
A naive ``Optional[str] = None`` would instead *accept* explicit ``null``, silently
loosening validation. To preserve the exact behavior we reconstruct the models the same
way with ``create_model`` (``index``/``id`` as ``(str, None)``; ``body`` as ``(Any, None)``,
which does accept ``None``). ``tests/tools/domains/test_generated_params.py`` pins this.
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

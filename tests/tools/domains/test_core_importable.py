# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Regression test: tools/domains/core.py is independently importable (no import cycle).

core.py used to top-import 35 handlers from tools.py while tools.py imported CORE_TOOLS
from core.py — a cycle that only resolved if tools.py was imported first. build_core_tools()
now imports handlers lazily, so core.py imports cleanly on its own. This pins that.
"""

import subprocess
import sys


def test_core_module_imports_first_in_fresh_interpreter():
    # Import core.py BEFORE tools.py in a clean interpreter — must not raise.
    code = (
        'import sys; sys.path.insert(0, "src"); '
        'import tools.domains.core as c; '
        'reg = c.build_core_tools(); '
        'assert "ListIndexTool" in reg and "ListClustersTool" in reg; '
        'print("OK", len(reg))'
    )
    result = subprocess.run(
        [sys.executable, '-c', code],
        capture_output=True,
        text=True,
        cwd=__import__('pathlib').Path(__file__).resolve().parents[3],
    )
    assert result.returncode == 0, f'core.py failed to import standalone:\n{result.stderr}'
    assert 'OK' in result.stdout

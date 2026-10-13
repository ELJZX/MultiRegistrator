"""Run the Qt widget smoke checks in a child process.

Importing Qt in the pytest process makes the interpreter abort during
finalization on some PySide6/Python builds, so the widgets are exercised in a
separate process that exits cleanly by itself.
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHILD = Path(__file__).with_name("gui_smoke_child.py")


def test_gui_widgets_smoke():
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, str(CHILD)],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = (result.stdout or "") + (result.stderr or "")

    # The child may abort while Windows detaches the Qt DLLs (a known PySide6
    # shutdown crash), so its exit code is not reliable.  The printed marker is.
    assert "GUI SMOKE FAILED" not in output, output
    assert "GUI SMOKE OK" in output, output

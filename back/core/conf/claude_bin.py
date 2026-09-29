# Claude Code CLI lookup (shared implementation in engine/tools/binaries.py, stdlib only).
#   python core/conf/claude_bin.py   -> prints the path (exit 1 if not found); used by launcher.py
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from engine.tools.binaries import find_cli, find_claude, command, WIN   # noqa: E402,F401

if __name__ == "__main__":
    found = find_claude(os.environ.get("VS_CLAUDE_BIN"))
    if not found:
        sys.exit(1)
    print(found)

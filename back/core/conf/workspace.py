# Access to the workspace's shared engine tools (local settings, machine details, CLI lookup) from the back venv.
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.tools import local_settings, machine   # noqa: E402,F401
from engine.tools.binaries import find_cli, command  # noqa: E402,F401

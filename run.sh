#!/usr/bin/env bash
# Video Studio — arranque en Linux/macOS.  ./run.sh [--port 8470] [--no-browser] [--install-engine] [--rebuild] [--lan]
set -euo pipefail
cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"   # uv / claude installed per user
if ! command -v uv >/dev/null 2>&1; then
  echo "[video-studio] Falta uv: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2; exit 1
fi
[ -x back/.venv/bin/python ] || uv venv back/.venv --python 3.12
exec back/.venv/bin/python launcher.py "$@"

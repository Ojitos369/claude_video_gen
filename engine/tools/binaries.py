# Locate a per-user CLI (claude, codex...). The service may start without the user's shell PATH (desktop launcher, systemd, a
# double-clicked run.bat), so besides PATH look in the usual install locations on Linux, macOS and Windows.
#   python core/conf/claude_bin.py   -> prints the path (exit 1 if not found); used by run.sh / run.bat
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

WIN = os.name == "nt"


def _npm_prefix():
    npm = shutil.which("npm.cmd" if WIN else "npm") or shutil.which("npm")
    if not npm:
        return None
    try:
        return subprocess.run([npm, "prefix", "-g"], capture_output=True, text=True, timeout=20).stdout.strip() or None
    except Exception:
        return None


def candidates(tool="claude"):
    home = Path.home()
    if WIN:
        env = lambda k: Path(os.environ.get(k, ""))
        yield from [home / f".local/bin/{tool}.exe", env("LOCALAPPDATA") / f"Programs/{tool}/{tool}.exe",
                    home / f".{tool}/local/{tool}.exe", env("APPDATA") / f"npm/{tool}.cmd", home / f"scoop/shims/{tool}.exe"]
        prefix = _npm_prefix()
        if prefix:
            yield Path(prefix) / f"{tool}.cmd"
    else:
        yield from [home / f".local/bin/{tool}", home / f".{tool}/local/{tool}", home / f".{tool}/local/node_modules/.bin/{tool}",
                    Path(f"/usr/local/bin/{tool}"), Path(f"/usr/bin/{tool}"), Path(f"/opt/homebrew/bin/{tool}"),
                    home / f".npm-global/bin/{tool}", home / f".bun/bin/{tool}", home / f".volta/bin/{tool}"]
        yield from (Path(p) for p in sorted(glob.glob(str(home / f".nvm/versions/node/*/bin/{tool}")), reverse=True))
        prefix = _npm_prefix()
        if prefix:
            yield Path(prefix) / f"bin/{tool}"


def find_cli(tool, preferred=None):
    """preferred (name or path) if it resolves, then PATH, then the known install locations. None if not installed."""
    for name in [preferred] if preferred else []:
        hit = shutil.which(name) or (name if os.path.isfile(name) else None)
        if hit:
            return os.path.abspath(hit)
    for name in ([f"{tool}.exe", f"{tool}.cmd", tool] if WIN else [tool]):
        hit = shutil.which(name)
        if hit:
            return os.path.abspath(hit)
    for p in candidates(tool):
        if p.is_file() and (WIN or os.access(p, os.X_OK)):
            return str(p)
    return None


def command(path):
    """argv prefix to run the CLI (a .cmd/.bat npm shim needs cmd.exe on Windows)."""
    return ["cmd.exe", "/c", path] if WIN and path.lower().endswith((".cmd", ".bat")) else [path]


def find_claude(preferred=None):
    return find_cli("claude", preferred)


if __name__ == "__main__":   # python binaries.py [tool]  -> path of the CLI (exit 1 if not found)
    tool = sys.argv[1] if len(sys.argv) > 1 else "claude"
    found = find_cli(tool, os.environ.get(f"{tool.upper()}_BIN"))
    if not found:
        sys.exit(1)
    print(found)

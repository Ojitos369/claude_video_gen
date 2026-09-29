# Video Studio launcher, shared by run.sh (Linux/macOS) and run.bat (Windows). Runs with back/.venv's python:
#   installs the back requirements when they change, rebuilds the front when its sources changed, checks the engine
#   environment, finds the Claude Code CLI, starts the service on 127.0.0.1 and opens the browser.
#   python launcher.py [--port 8470] [--no-browser] [--install-engine] [--rebuild] [--lan]
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
WIN = os.name == "nt"
BACK = os.path.join(ROOT, "back")
VENV_PY = os.path.join(BACK, ".venv", "Scripts" if WIN else "bin", "python.exe" if WIN else "python")
ENGINE_PY = os.path.join(ROOT, ".venv", "Scripts" if WIN else "bin", "python.exe" if WIN else "python")
DIST = os.path.join(BACK, "media", "dist", "index.html")

def say(msg): print(f"[video-studio] {msg}", flush=True)

def run(cmd, cwd=ROOT):
    say("$ " + " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True, shell=WIN and cmd[0] in ("pnpm", "npm"))

def which(name):
    """PATH first, then usual per-user install dirs (nvm, pnpm, volta, npm global). The tool's folder is added to PATH
    so node-based tools (pnpm from nvm) also find `node`."""
    hit = (shutil.which(name + ".cmd") if WIN else None) or shutil.which(name)
    if hit:
        return hit
    import glob
    home = os.path.expanduser("~")
    if WIN:
        dirs = [os.path.join(os.environ.get("APPDATA", ""), "npm"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "pnpm"),
                os.path.join(home, ".local", "bin"), os.path.join(home, "scoop", "shims")]
        names = [name + ".cmd", name + ".exe", name]
    else:
        dirs = [os.path.join(home, ".local", "share", "pnpm"), os.path.join(home, ".local", "bin"), os.path.join(home, ".volta", "bin"),
                os.path.join(home, ".npm-global", "bin"), os.path.join(home, ".bun", "bin")]
        dirs += sorted(glob.glob(os.path.join(home, ".nvm", "versions", "node", "*", "bin")), reverse=True)
        names = [name]
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
                return p
    return None

def back_requirements():
    req = os.path.join(BACK, "requirements.txt")
    stamp = os.path.join(BACK, ".venv", ".requirements.sha")
    digest = hashlib.sha256(open(req, "rb").read()).hexdigest()
    if os.path.exists(stamp) and open(stamp).read() == digest:
        return
    run([which("uv") or "uv", "pip", "install", "--python", VENV_PY, "-r", req])
    open(stamp, "w").write(digest)

def front_needs_build():
    if not os.path.exists(DIST):
        return True
    built = os.path.getmtime(DIST)
    for base in ("src", "index.html", "package.json", "vite.config.js"):
        p = os.path.join(ROOT, "front", base)
        paths = [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs] if os.path.isdir(p) else [p]
        if any(os.path.exists(x) and os.path.getmtime(x) > built for x in paths):
            return True
    return False

def build_front(force):
    if not (force or front_needs_build()):
        return
    pnpm = which("pnpm")
    if not pnpm:
        if os.path.exists(DIST):
            say("front/ cambió pero no hay pnpm: uso el front ya compilado (instala pnpm para recompilar)")
            return
        sys.exit("[video-studio] Falta pnpm para compilar el front: https://pnpm.io/installation")
    front = os.path.join(ROOT, "front")
    if not os.path.isdir(os.path.join(front, "node_modules")):
        run([pnpm, "install"], cwd=front)
    run([pnpm, "build"], cwd=front)
    run([VENV_PY, os.path.join(ROOT, "migrate_view.py")])

def engine_env(install):
    if os.path.exists(ENGINE_PY):
        return
    if install:
        uv = which("uv") or "uv"
        run([uv, "venv", os.path.join(ROOT, ".venv"), "--python", "3.11"])
        run([uv, "pip", "install", "--python", ENGINE_PY, "-r", os.path.join(ROOT, "requirements.txt")])
    else:
        say("AVISO: falta el entorno del motor (.venv). La app arranca, pero Claude no podrá renderizar videos.")
        say("       Instálalo con:  run.sh --install-engine  /  run.bat --install-engine  (descarga torch con CUDA, ~5 GB)")

def find_claude():
    sys.path.insert(0, BACK)
    from core.conf.claude_bin import find_claude as fc, command
    path = fc(os.environ.get("VS_CLAUDE_BIN"))
    if not path:
        sys.exit("[video-studio] No encontré Claude Code. Instálalo (https://docs.claude.com/en/docs/claude-code) "
                 "e inicia sesión con `claude`, o define VS_CLAUDE_BIN con la ruta del ejecutable.")
    try:
        ver = subprocess.run(command(path) + ["--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        ver = "?"
    say(f"Claude Code: {path} ({ver})")
    return path

def running(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/base/status", timeout=2); return True
    except Exception:
        return False

def open_when_ready(url, port):
    for _ in range(120):
        if running(port):
            webbrowser.open(url); return
        time.sleep(0.5)

def main():
    ap = argparse.ArgumentParser(description="Arranca Video Studio en local")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8470)))
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--install-engine", action="store_true", help="instala también el entorno del motor (.venv, torch CUDA)")
    ap.add_argument("--rebuild", action="store_true", help="recompila el front aunque no haya cambios")
    ap.add_argument("--lan", action="store_true", help="escuchar también en la red local (acceso desde el teléfono, con token)")
    a = ap.parse_args()
    url = f"http://127.0.0.1:{a.port}"
    if running(a.port):
        say(f"Video Studio ya está corriendo en {url}")
        if not a.no_browser: webbrowser.open(url)
        return
    back_requirements()
    build_front(a.rebuild)
    engine_env(a.install_engine)
    os.environ["VS_CLAUDE_BIN"] = find_claude()
    sys.path.insert(0, ROOT)
    from engine.tools import local_settings, machine
    m, updated = machine.ensure()          # settings.local.json -> machine, only when missing or changed
    say(f"Equipo {'detectado y guardado' if updated else 'sin cambios'}: {machine.summary(m)}")
    st = local_settings.load()
    if a.lan and not st["access"]["lan"]:
        local_settings.update({"access": {"lan": True}}); st = local_settings.load()
    host = "0.0.0.0" if st["access"]["lan"] else "127.0.0.1"
    if host == "0.0.0.0":
        import socket
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sk.connect(("10.255.255.255", 1)); ip = sk.getsockname()[0]
        except OSError:
            ip = "127.0.0.1"
        finally:
            sk.close()
        say(f"Acceso desde el teléfono (misma red): http://{ip}:{a.port}/?token={st['access']['token']}")
        say("  (también como QR en Ajustes -> Acceso desde el teléfono)" + ("; si Windows lo pregunta, permite Python en el firewall para redes privadas" if WIN else ""))
    if not shutil.which("ffmpeg"):
        say("AVISO: no encontré ffmpeg en el PATH (el motor lo necesita para codificar)")
    if not a.no_browser:
        threading.Thread(target=open_when_ready, args=(url, a.port), daemon=True).start()
    say(f"Servidor en {url}  (Ctrl+C para detener)")
    try:
        subprocess.run([VENV_PY, "-m", "uvicorn", "main:app", "--host", host, "--port", str(a.port)], cwd=BACK)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()

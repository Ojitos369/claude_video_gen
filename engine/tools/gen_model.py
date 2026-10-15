# 3D model tool for video projects: Claude writes a Blender Python (bpy) script, this runs it headless and exports the model.
# Blender binary: settings.local.json -> models3d.bin (default ~/Documents/apps/blender/blender; BLENDER_BIN overrides).
#   python engine/tools/gen_model.py <project> --script assets/model.py --out assets/robot.glb [--preview assets/robot.png]
#          [--turntable assets/robot_turn 36] [--engine CYCLES|BLENDER_EEVEE|BLENDER_WORKBENCH] [--res 768]
# The script runs in an empty scene and only builds the model (meshes, materials); it must not export, render or save.
# --preview writes 3 views (<name>.png 3/4, _back, _side); --turntable N frames 0000.png.. for clips (ffmpeg -> video).
# Formats by --out extension: .glb .gltf .obj .fbx .stl .ply .blend. Logged in assets/models.json (max models3d.max_per_project);
# script, request and Blender's output are kept in assets/blender/ (engine/tools/apilog.py).
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from engine.tools import local_settings  # noqa: E402
from engine.tools.apilog import Call  # noqa: E402

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender_run.py")


def main():
    ap = argparse.ArgumentParser(description="Genera un modelo 3D con Blender (script bpy)")
    ap.add_argument("project"); ap.add_argument("--script", required=True, help="script bpy dentro del proyecto")
    ap.add_argument("--out", required=True, help="modelo de salida, p. ej. assets/robot.glb")
    ap.add_argument("--preview", help="PNG de vista previa (también _back y _side)")
    ap.add_argument("--turntable", nargs=2, metavar=("DIR", "N"), help="carpeta y número de cuadros de giro 360°")
    ap.add_argument("--engine", help="CYCLES (default) | BLENDER_EEVEE | BLENDER_WORKBENCH"); ap.add_argument("--res", type=int, default=768)
    ap.add_argument("--note", default="", help="para qué es el modelo (queda en models.json)")
    a = ap.parse_args()
    s = local_settings.load(); cfg = s["models3d"]
    proj = a.project if os.path.isdir(a.project) else os.path.join(local_settings.ROOT, "projects", a.project)
    if not os.path.isdir(proj): raise SystemExit(f"no existe el proyecto {a.project}")
    blender = local_settings.blender_bin()
    if not blender: raise SystemExit("No encontré Blender: configura la ruta en los ajustes de la app (Modelos 3D) o BLENDER_BIN")
    j = lambda p: p if os.path.isabs(p) else os.path.join(proj, p)
    script, out = j(a.script), j(a.out)
    if not os.path.isfile(script): raise SystemExit(f"no existe el script {a.script}")
    log_path = os.path.join(proj, "assets", "models.json")
    log = json.load(open(log_path, encoding="utf-8")) if os.path.exists(log_path) else []
    if len({e["file"] for e in log}) >= int(cfg.get("max_per_project") or 6) and os.path.relpath(out, proj) not in {e["file"] for e in log}:
        raise SystemExit(f"Límite de {cfg.get('max_per_project')} modelos por proyecto alcanzado (ajustes -> Modelos 3D)")
    cmd = [blender, "-b", "--factory-startup", "-P", RUNNER, "--", script, out, "--res", str(a.res), "--engine", a.engine or cfg.get("engine") or "CYCLES"]
    if a.preview: cmd += ["--preview", j(a.preview)]
    if a.turntable: cmd += ["--turntable", j(a.turntable[0]), a.turntable[1]]
    rec = Call(proj, "blender", {"command": "blender -b -P blender_run.py", "script": os.path.relpath(script, proj), "out": os.path.relpath(out, proj),
                                 "args": cmd[cmd.index("--") + 3:]})
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=540)
    rec.response({"stdout": r.stdout[-6000:], "stderr": r.stderr[-3000:]}, returncode=r.returncode)
    rec.file(script)
    if r.returncode or not os.path.exists(out):
        lines = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()]
        raise SystemExit("Blender falló:\n" + "\n".join(lines[-25:]))
    info = next((l for l in r.stdout.splitlines() if l.startswith("MODEL ")), "")
    log.append({"file": os.path.relpath(out, proj), "script": os.path.relpath(script, proj), "note": a.note, "info": info[6:],
                "preview": a.preview, "turntable": a.turntable and a.turntable[0], "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    json.dump(log, open(log_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{os.path.relpath(out, proj)} ({os.path.getsize(out) / 1024:.0f} KB) {info[6:]}")


if __name__ == "__main__":
    main()

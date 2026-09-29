# Machine details (OS, CPU, RAM, GPU, video encoders, headless OpenGL, disk). Detected when the service starts and stored in
# the "machine" section of settings.local.json only when missing or when the hardware / drivers changed (fingerprint).
# Nothing about the host is hard-coded anywhere else: the engine and Claude read it from there. Stdlib only, Linux + Windows.
#   python engine/tools/machine.py [--force]   -> prints the stored details (detects them first when needed)
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from engine.tools import local_settings  # noqa: E402

WIN = os.name == "nt"
ENCODERS = ["h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox", "libx264"]   # preference order


def _run(cmd, timeout=20):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def cpu_name():
    if WIN:
        name = _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"]).strip()
        return name or platform.processor()
    try:
        with open("/proc/cpuinfo") as f:
            m = re.search(r"model name\s*:\s*(.+)", f.read())
            if m: return m.group(1).strip()
    except OSError:
        pass
    return _run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip() or platform.processor()


def ram_gb():
    if WIN:
        import ctypes
        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS(); m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return round(m.ullTotalPhys / 2 ** 30, 1)
    try:
        with open("/proc/meminfo") as f:
            return round(int(re.search(r"MemTotal:\s+(\d+)", f.read()).group(1)) / 2 ** 20, 1)
    except (OSError, AttributeError):
        out = _run(["sysctl", "-n", "hw.memsize"]).strip()
        return round(int(out) / 2 ** 30, 1) if out.isdigit() else None


def gpus():
    res = []
    smi = shutil.which("nvidia-smi")
    if smi:
        out = _run([smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"])
        cuda = re.search(r"CUDA Version:\s*([\d.]+)", _run([smi]))
        for line in out.strip().splitlines():
            name, mem, drv = [x.strip() for x in line.split(",")[:3]]
            res.append({"vendor": "nvidia", "name": name, "vram_gb": round(float(mem) / 1024, 1), "driver": drv,
                        "cuda": cuda.group(1) if cuda else None})
    if not res and WIN:
        out = _run(["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + '|' + $_.AdapterRAM }"])
        for line in out.strip().splitlines():
            name, _, ram = line.partition("|")
            res.append({"vendor": "other", "name": name.strip(), "vram_gb": round(int(ram) / 2 ** 30, 1) if ram.strip().isdigit() else None})
    if not res and shutil.which("lspci"):
        for line in _run(["lspci"]).splitlines():
            if re.search(r"VGA|3D controller", line):
                res.append({"vendor": "other", "name": line.split(":", 2)[-1].strip(), "vram_gb": None})
    return res


def ffmpeg_info():
    ff = shutil.which("ffmpeg")
    if not ff:
        return {"ffmpeg": None, "encoders": [], "video_encoder": None}
    version = (_run([ff, "-version"]).splitlines() or [""])[0]
    listed = _run([ff, "-hide_banner", "-encoders"])
    working = []
    for enc in ENCODERS:   # an encoder can be listed but unusable (no GPU / driver): try one tiny frame
        if f" {enc} " not in listed: continue
        r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                            "-frames:v", "1", "-c:v", enc, "-f", "null", "-"], capture_output=True, timeout=60)
        if r.returncode == 0: working.append(enc)
    return {"ffmpeg": version, "encoders": working, "video_encoder": working[0] if working else None}


def headless_gl():
    if WIN or sys.platform == "darwin":
        return "wgl" if WIN else "cgl"
    import ctypes.util
    return "egl" if ctypes.util.find_library("EGL") else None


def detect():
    import shutil as sh
    total, _, free = sh.disk_usage(local_settings.ROOT)
    g = gpus()
    ff = ffmpeg_info()
    cores = os.cpu_count() or 1
    m = {
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}", "os_detail": platform.platform(), "arch": platform.machine(),
        "python": platform.python_version(),
        "cpu": cpu_name(), "cpu_cores": cores, "ram_gb": ram_gb(),
        "gpus": g, "cuda": bool(g and g[0].get("cuda")),
        **ff,
        "headless_gl": headless_gl(),
        "disk_free_gb": round(free / 2 ** 30, 1), "disk_total_gb": round(total / 2 ** 30, 1),
        "engine_venv": os.path.exists(os.path.join(local_settings.ROOT, ".venv")),
    }
    vram = (g[0].get("vram_gb") or 0) if g else 0
    # parallel render workers: bounded by CPU cores, RAM (~1.5 GB each) and, for GPU encoders, a conservative VRAM share
    by_ram = int((m["ram_gb"] or 8) // 1.5)
    by_vram = int(vram // 1) if m["video_encoder"] and m["video_encoder"] != "libx264" else 99
    m["render_jobs"] = max(1, min(8, cores // 3 or 1, by_ram, by_vram))
    stable = {k: m[k] for k in ("hostname", "os", "arch", "cpu", "cpu_cores", "ram_gb", "gpus", "ffmpeg", "encoders", "headless_gl")}
    m["fingerprint"] = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()[:16]
    m["detected_at"] = datetime.now().isoformat(timespec="seconds")
    return m


def ensure(force=False):
    """Refresh settings.local.json -> machine when missing or when the machine changed. Returns (machine, updated)."""
    s = local_settings.load()
    cur = s.get("machine") or {}
    new = detect()
    if not force and cur.get("fingerprint") == new["fingerprint"]:
        if cur.get("disk_free_gb") != new["disk_free_gb"] or cur.get("engine_venv") != new["engine_venv"]:
            cur.update(disk_free_gb=new["disk_free_gb"], engine_venv=new["engine_venv"]); s["machine"] = cur; local_settings.save(s)
        return cur, False
    s["machine"] = new
    local_settings.save(s)
    return new, True


def summary(m=None):
    """One paragraph for prompts / the UI."""
    m = m or (local_settings.load().get("machine") or ensure()[0])
    g = ", ".join(f"{x['name']}" + (f" {x['vram_gb']} GB VRAM" if x.get("vram_gb") else "") + (f", CUDA {x['cuda']}" if x.get("cuda") else "")
                  for x in m.get("gpus", [])) or "sin GPU dedicada detectada"
    return (f"{m.get('os')} ({m.get('arch')}), CPU {m.get('cpu')} ({m.get('cpu_cores')} hilos), RAM {m.get('ram_gb')} GB, GPU: {g}. "
            f"Codificador de video: {m.get('video_encoder') or 'ninguno (falta ffmpeg)'} (disponibles: {', '.join(m.get('encoders') or []) or '-'}). "
            f"OpenGL sin ventana: {m.get('headless_gl') or 'no disponible'}. Procesos de render en paralelo recomendados: {m.get('render_jobs')}. "
            f"Disco libre: {m.get('disk_free_gb')} GB.")


if __name__ == "__main__":
    m, updated = ensure("--force" in sys.argv)
    print(("actualizado" if updated else "sin cambios") + ": " + summary(m))

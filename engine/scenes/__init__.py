# Scene registry: every sc_<name> function in engine/scenes/*.py (and in a project's own scenes.py) becomes motif <name>.
import importlib, importlib.util, os, pkgutil
from . import base

def _collect(mod, out):
    out.update({k[3:]: f for k, f in vars(mod).items() if k.startswith("sc_") and callable(f)})

def load(project_dir=None, bw=540, bh=960, palette=None):
    base.BW, base.BH = bw, bh
    for k, v in (palette or {}).items():
        setattr(base, k.upper(), tuple(v))
    base.grad.cache_clear()
    scenes = {}
    for m in pkgutil.iter_modules(__path__):
        if m.name == "base": continue
        mod = importlib.import_module(f"{__name__}.{m.name}")
        for k in ["BW", "BH"] + [n.upper() for n in (palette or {})]:   # modules did `from .base import *`
            if hasattr(mod, k): setattr(mod, k, getattr(base, k))
        _collect(mod, scenes)
    custom = os.path.join(project_dir or "", "scenes.py")
    if project_dir and os.path.exists(custom):
        spec = importlib.util.spec_from_file_location("project_scenes", custom)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        _collect(mod, scenes)
    return scenes

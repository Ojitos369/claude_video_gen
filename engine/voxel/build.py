# Build every voxel scene of a project into render/voxcache/<index>.npz (+ dust / dust_up and meta.json).
#   python engine/voxel/build.py <project> [--only 3 5] [--jobs 3]
# voxscenes.py must define SCENES = [{"name", "build": f(grid), "look": {...}, "cam": f(u) -> (pos, target)}],
# and optionally GRID = dict(R=64, ymin=-24, ymax=72, vs=0.4), BUDGET = 600_000.
import argparse, json, os, sys, time
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import project_from_argv
import numpy as np
from engine.voxel import vox
from engine.voxel.show import load_scenes

pr = project_from_argv()
ap = argparse.ArgumentParser(); ap.add_argument("--only", nargs="*", type=int); ap.add_argument("--jobs", type=int, default=3)
a = ap.parse_args()
mod = load_scenes(pr)
GRID = {**dict(R=64.0, ymin=-24.0, ymax=72.0, vs=0.4), **getattr(mod, "GRID", {})}
BUDGET = getattr(mod, "BUDGET", 600_000)
out = pr.p("render", "voxcache"); os.makedirs(out, exist_ok=True)

def build(i):
    t0 = time.time()
    g = vox.Grid(**GRID)
    mod.SCENES[i]["build"](g)
    t1 = time.time()
    pack, n = vox.finalize(g, BUDGET)
    np.savez(os.path.join(out, f"raw_{i}.npz"), n=n, **pack)
    return i, n, int((g.mat > 0).sum()), t1 - t0, time.time() - t1

if __name__ == "__main__":
    todo = a.only if a.only is not None else list(range(len(mod.SCENES)))
    with Pool(a.jobs) as pool:
        for i, n, tot, tb, tf in pool.imap_unordered(build, todo):
            print(f"scene {i:2d} {mod.SCENES[i]['name']:<18} voxels {tot:>9,}  visible {n:>8,}  build {tb:5.1f}s  finalize {tf:5.1f}s", flush=True)
    counts = {i: int(np.load(os.path.join(out, f"raw_{i}.npz"))["n"]) for i in range(len(mod.SCENES))}
    N = max(counts.values())
    R = GRID["R"]
    for i in range(len(mod.SCENES)):
        d = np.load(os.path.join(out, f"raw_{i}.npz")); pack = {k: d[k] for k in d.files if k != "n"}
        np.savez(os.path.join(out, f"{i}.npz"), **vox.pad(pack, counts[i], N, R, seed=i))
    # dust: every voxel hidden in a cloud (first scene assembles from it, last scene dissolves upward into it)
    # dust clouds reuse the colours of the scene they assemble into / dissolve from, compact above the centre
    r = np.random.default_rng(99)
    for key, y0, y1, src in (("dust", 8, 40, 0), ("dust_up", 50, 90, len(mod.SCENES) - 1)):
        ang = r.uniform(0, 2 * np.pi, N); rad = np.sqrt(r.uniform(0, 1, N)) * R * .55
        pos = np.stack([rad * np.cos(ang), r.uniform(y0, y1, N), rad * np.sin(ang), np.zeros(N)], 1).astype(np.float32)
        col = np.load(os.path.join(out, f"{src}.npz"))["col"]
        np.savez(os.path.join(out, f"{key}.npz"), pos=pos, col=col,
                 nrm=np.tile(np.array([128, 255, 128, 10], np.uint8), (N, 1)), misc=np.zeros((N, 4), np.uint8),
                 lit=np.zeros((N, 4), np.uint8), mot=np.zeros((N, 4), np.float16))
    json.dump({"N": int(N), "R": R, "vs": GRID["vs"], "counts": counts, "names": [s["name"] for s in mod.SCENES]},
              open(os.path.join(out, "meta.json"), "w"), indent=1)
    print("N =", N)

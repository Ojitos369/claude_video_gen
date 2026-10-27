# Cuts a spritesheet (frames of one animation) into PNG frames aligned on a common canvas, and optionally builds a GIF.
#   python engine/tools/split_sheet.py <project> assets/walk_sheet.png [--grid 4x2] [--out assets/sprites/walk] [--gif out/walk.gif] [--fps 12]
# --grid CxR cuts a uniform grid (row-major); without it, frames are the alpha connected components (rows top->bottom, then left->right).
# Sheets with real alpha (gen_image.py --transparent, OpenAI) are used as is; opaque sheets (Gemini, flat background) are keyed
# from the border colour. Every frame shares the same size and is anchored bottom-centre, so the character does not jitter.
import argparse
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from engine.tools import local_settings


def to_rgba(im, tol):
    a = np.asarray(im.convert("RGBA")).astype(np.int16)
    if (a[..., 3] < 250).mean() > 0.05: return a   # already transparent
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])[:, :3]
    bg = np.median(edge, axis=0)
    near = np.abs(a[..., :3] - bg).max(2) < tol
    lab, _ = ndimage.label(near)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    a[..., 3] = np.where(np.isin(lab, border[border > 0]), 0, 255)   # only background connected to the border
    return a


def frames_of(a, grid, min_area):
    if grid:
        c, r = map(int, grid.lower().split("x"))
        h, w = a.shape[0] // r, a.shape[1] // c
        return [a[y * h:(y + 1) * h, x * w:(x + 1) * w] for y in range(r) for x in range(c)]
    lab, n = ndimage.label(ndimage.binary_dilation(a[..., 3] > 24, iterations=6))   # dilation joins loose bits of one frame
    boxes = [s for s in ndimage.find_objects(lab) if (s[0].stop - s[0].start) * (s[1].stop - s[1].start) >= min_area]
    hs = np.median([s[0].stop - s[0].start for s in boxes])
    boxes.sort(key=lambda s: (round(s[0].start / hs), s[1].start))   # row bands, then left to right
    return [a[s] for s in boxes]


def main():
    ap = argparse.ArgumentParser(description="Corta una spritesheet en cuadros PNG alineados y arma un GIF")
    ap.add_argument("project"); ap.add_argument("sheet")
    ap.add_argument("--grid", help="columnas x filas, p. ej. 4x2 (sin esto: componentes conexos del alfa)")
    ap.add_argument("--out", help="carpeta de los cuadros (default assets/sprites/<nombre de la hoja>)")
    ap.add_argument("--gif", help="ruta del GIF, p. ej. out/walk.gif")
    ap.add_argument("--fps", type=float, default=12)
    ap.add_argument("--tol", type=int, default=40, help="tolerancia del fondo plano (hojas sin alfa)")
    ap.add_argument("--min-area", type=int, default=400, help="área mínima de un cuadro (modo sin --grid)")
    a = ap.parse_args()
    proj = a.project if os.path.isdir(a.project) else os.path.join(local_settings.ROOT, "projects", a.project)
    p = lambda x: x if os.path.isabs(x) else os.path.join(proj, x)
    stem = os.path.splitext(os.path.basename(a.sheet))[0]
    out = p(a.out or os.path.join("assets", "sprites", stem))
    os.makedirs(out, exist_ok=True)
    cells = []
    for f in frames_of(to_rgba(Image.open(p(a.sheet)), a.tol), a.grid, a.min_area):
        ys, xs = np.nonzero(f[..., 3] > 8)
        if len(ys): cells.append(f[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    if not cells: raise SystemExit("no se encontraron cuadros")
    W, H = max(c.shape[1] for c in cells), max(c.shape[0] for c in cells)
    frames = []
    for i, c in enumerate(cells):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        im.paste(Image.fromarray(c.clip(0, 255).astype(np.uint8)), ((W - c.shape[1]) // 2, H - c.shape[0]))
        im.save(os.path.join(out, f"{stem}_{i:02d}.png")); frames.append(im)
    print(f"{len(frames)} cuadros {W}x{H} -> {os.path.relpath(out, proj)}")
    if a.gif:
        g = p(a.gif); os.makedirs(os.path.dirname(g), exist_ok=True)
        frames[0].save(g, save_all=True, append_images=frames[1:], duration=round(1000 / a.fps), loop=0, disposal=2)
        print(f"GIF {os.path.relpath(g, proj)} ({a.fps:g} fps)")


if __name__ == "__main__":
    main()

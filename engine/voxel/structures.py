# Reusable voxel structures (steampunk / industrial). All sizes in world units; g is an engine.voxel.vox.Grid.
import math
import numpy as np
from engine.voxel.vox import (SOLID, WATER, FOLIAGE, GLASS, STEAM, LAVA, METAL, BRASS, BASS, MID, HIGH, CHASE,
                              SPIN_Y, SPIN_Z, SPIN_X, BOB, hexc, fbm, vn)

BRASS_C, COPPER, VERDI, IRON, RUST = hexc("#c9a045"), hexc("#b8683a"), hexc("#4f9a86"), hexc("#3c3d44"), hexc("#8a4a2a")
BRICK, SOOT, WOOD, IVORY, LAMP = hexc("#8c3b2a"), hexc("#2a2524"), hexc("#6b4a2e"), hexc("#e8dcc0"), hexc("#ffc062")
FURN, STEAM_C, GLASS_C, LEATHER = hexc("#ff6a1a"), hexc("#d8d2c8"), hexc("#9fd6d0"), hexc("#7a4b30")

def mixc(a, b, t): return a + (b - a) * np.clip(t, 0, 1)[..., None] if np.ndim(t) else a + (b - a) * t

def noisy(c1, c2, scale=0.15, seed=0):
    """Painter: big low-frequency patches between two colours (per-voxel jitter is added by Grid.put)."""
    return lambda x, y, z: mixc(c1, c2, fbm(x * scale, z * scale, 3, seed, y * scale))

def brass_worn(seed=0): return noisy(BRASS_C, hexc("#8a6a2a"), 0.2, seed)
def copper_patina(seed=0): return lambda x, y, z: mixc(COPPER, VERDI, np.clip(fbm(x * .25, z * .25, 3, seed, y * .25) * 1.8 - .6, 0, 1))
def bricks(seed=0):
    def p(x, y, z):
        row = np.floor(y / 0.8); joint = (np.abs(((x + z + row * 0.6) % 1.6) - 0.8) < 0.12) | (np.abs(y % 0.8) < 0.12)
        base = mixc(BRICK, hexc("#6e2c20"), fbm(x * .3, z * .3, 2, seed, y * .3))
        return np.where(joint[:, None], hexc("#4a3a33"), base)
    return p

def ground_paint(grass=hexc("#5a6a3a"), dirt=hexc("#6b5038"), rock=hexc("#5c5552"), seed=0):
    def p(x, y, z, top):
        d = top - y
        c = mixc(dirt, rock, np.clip(d / 3, 0, 1))
        c = np.where((d < 0.5)[:, None], mixc(grass, hexc("#7a6a3a"), fbm(x * .1, z * .1, 3, seed)), c)
        return c
    return p

def cobble_paint(seed=0):
    def p(x, y, z, top):
        cell = vn(x * 1.1, z * 1.1, seed)
        edge = (np.abs((x * 1.1) % 1 - .5) > .42) | (np.abs((z * 1.1) % 1 - .5) > .42)
        c = mixc(hexc("#6a625a"), hexc("#8a7a66"), cell)
        c = np.where(edge[:, None], hexc("#3a3430"), c)
        return np.where(((top - y) > 0.5)[:, None], hexc("#4a4440"), c)
    return p

# ---------------------------------------------------------------- structures
def lamp(g, x, y, z, h=3.0, phase=0.0, grp=CHASE):
    g.cyl((x, y + h / 2, z), .18, h, IRON, mat=METAL)
    g.box((x, y + h + .3, z), (.8, .8, .8), LAMP, mat=GLASS, glow=.9, grp=grp, phase=phase)
    g.cone((x, y + h + .7, z), .6, .5, BRASS_C, mat=BRASS)

def chimney(g, x, y, z, h, r, smoke=True, seed=0):
    g.cyl((x, y + h / 2, z), r, h, bricks(seed), shell=0.8)
    g.cyl((x, y + h + .3, z), r + .4, .8, IRON, mat=METAL)
    g.cyl((x, y + h - .2, z), r - .6, .4, FURN, mat=LAVA, glow=.8, grp=BASS)
    if smoke:
        r_ = np.random.default_rng(abs(int(seed)))
        for k in range(7):
            m = g.motion(BOB, .8 + k * .15, r_.uniform(0, 6), .6 + r_.uniform(0, .5))
            yy = y + h + 2 + k * 2.6; rr = r * (0.9 + k * .35)
            g.ell((x + k * .9, yy, z + math.sin(k) * .8), (rr, rr * .7, rr), STEAM_C, mat=STEAM, mot=m, jitter=.04)

def big_gear(g, c, R, th=1.2, axis="z", speed=0.3, teeth=None, color=None, **k):
    px, py, pz = c
    kind = {"y": SPIN_Y, "z": SPIN_Z, "x": SPIN_X}[axis]
    p1, p2 = {"y": (px, pz), "z": (px, py), "x": (py, pz)}[axis]
    m = g.motion(kind, p1, p2, speed)
    g.gear(c, R, th, brass_worn(int(R * 10)) if color is None else color, axis=axis, teeth=teeth or max(10, int(R * 3)), mat=BRASS, mot=m, **k)

def pipe(g, pts, r=.6, color=None, flanges=True):
    g.tube([(x, y, z, r) for x, y, z in pts], copper_patina(3) if color is None else color, mat=METAL)
    if flanges:
        for (x0, y0, z0), (x1, y1, z1) in zip(pts, pts[1:]):
            for u in (0.1, 0.9):
                x, y, z = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, z0 + (z1 - z0) * u
                g.ell((x, y, z), (r * 1.35, r * 1.35, r * 1.35), BRASS_C, mat=BRASS)

def tower(g, x, z, y, h, r, square=False, roof="cone", clock=False, seed=0, win_grp=MID):
    wall = bricks(seed) if seed % 2 == 0 else noisy(hexc("#7a6a5a"), hexc("#5a4a3e"), .2, seed)
    if square: g.box((x, y + h / 2, z), (2 * r, h, 2 * r), wall)
    else: g.cyl((x, y + h / 2, z), r, h, wall)
    for lvl in range(int(h // 4)):   # lit windows, one ring per level
        yy = y + 2.5 + lvl * 4
        for a in range(8 if r > 3 else 4):
            ang = a / (8 if r > 3 else 4) * 2 * math.pi + lvl * .3
            wx, wz = x + (r + .05) * math.cos(ang), z + (r + .05) * math.sin(ang)
            lit = (seed * 7 + lvl * 3 + a) % 3 != 0
            g.box((wx, yy, wz), (.9, 1.5, .9), LAMP if lit else SOOT, mat=GLASS, glow=.75 if lit else 0, grp=win_grp,
                  phase=((lvl * 8 + a) % 16) / 16)
    g.cyl((x, y + h + .3, z), r + .6, .8, BRASS_C, mat=BRASS)
    if roof == "cone": g.cone((x, y + h + .7, z), r + .3, r * 2.2, copper_patina(seed), mat=METAL)
    elif roof == "dome": g.ell((x, y + h + .7, z), (r, r * .9, r), copper_patina(seed), mat=METAL)
    g.cyl((x, y + h + r * 2.2 + 1.5, z), .12, 3, BRASS_C, mat=BRASS)
    if clock:
        cz = z - r - .3
        g.cyl((x, y + h - 3, cz), r * .8, .5, IVORY, axis="z")
        g.torus((x, y + h - 3, cz - .2), r * .8, .3, BRASS_C, axis="z", mat=BRASS)
        for hand, L, sp in (("h", r * .45, .05), ("m", r * .7, .4)):
            m = g.motion(SPIN_Z, x, y + h - 3, sp)
            g.tube([(x, y + h - 3, cz - .5, .22), (x, y + h - 3 + L, cz - .5, .15)], SOOT, mat=METAL, mot=m)

def house(g, x, z, y, w, d, h, seed=0):
    g.box((x, y + h / 2, z), (w, h, d), bricks(seed) if seed % 3 else noisy(WOOD, hexc("#4a3222"), .3, seed))
    for i in range(int(w // 2.5)):
        for s in (-1, 1):
            lit = (seed + i) % 2 == 0
            g.box((x - w / 2 + 1.5 + i * 2.5, y + h * .6, z + s * (d / 2 + .05)), (1, 1.4, .4), LAMP if lit else SOOT, mat=GLASS,
                  glow=.7 if lit else 0, grp=MID, phase=(i % 8) / 8)
    for k in range(int(h), int(h + w / 2) + 1):   # pitched roof
        t = (k - h) / (w / 2 + .01)
        g.box((x, y + k, z), (w * (1 - t) + .6, 1.0, d + .6), copper_patina(seed) if seed % 2 else hexc("#4a3a3a"), mat=METAL)
    chimney(g, x + w * .25, y + h, z, 3 + seed % 3, .6, smoke=seed % 2 == 0, seed=seed)

def airship(g, c, L=14, orbit=None, speed=0.08, seed=0):
    """Balloon + brass bands + gondola + fins + propeller. orbit=(cx, cz) makes it circle the scene."""
    cx, cy, cz = c
    m = g.motion(SPIN_Y, orbit[0], orbit[1], speed) if orbit else g.motion(BOB, .6, seed, .5)
    fab = [hexc("#b04a3a"), hexc("#d8c09a"), hexc("#5a6a8a")][seed % 3]
    g.ell((cx, cy, cz), (L / 2, L / 5, L / 5), lambda x, y, z: np.where(((np.abs((x - cx) % 3 - 1.5) < .2))[:, None], BRASS_C, fab), mot=m, jitter=.04)
    g.box((cx, cy - L / 5 - 1.2, cz), (L * .35, 1.4, 2.0), WOOD, mot=m)
    g.box((cx, cy - L / 5 - 1.2, cz - 1.05), (L * .3, .5, .2), LAMP, mat=GLASS, glow=.8, grp=CHASE, phase=seed * .2, mot=m)
    for s in (-1, 1):
        g.tube([(cx - L * .15, cy - L / 5 + .3, cz + s * .8, .12), (cx - L * .15, cy - L / 5 - .6, cz + s * .8, .12)], IRON, mat=METAL, mot=m)
    g.box((cx - L / 2 + .5, cy, cz), (2, L / 5 * 1.4, .4), fab * .8, mot=m)
    g.box((cx - L / 2 + .5, cy, cz), (2, .4, L / 5 * 1.4), fab * .8, mot=m)
    g.box((cx + L * .2, cy - L / 5 - 1.2, cz), (.5, 3.0, .3), BRASS_C, mat=BRASS, mot=m)   # propeller blade

def bridge(g, p0, p1, y, w=4.0, arches=4, lamps=True):
    (x0, z0), (x1, z1) = p0, p1
    L = math.hypot(x1 - x0, z1 - z0); ux, uz = (x1 - x0) / L, (z1 - z0) / L
    n = int(L / 0.4)
    for i in range(n + 1):
        t = i / n; x, z = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
        g.box((x, y, z), (w if abs(uz) > .7 else .6, 1.0, w if abs(ux) > .7 else .6), noisy(hexc("#6a5a4a"), hexc("#4a4038"), .3))
    for a in range(arches):
        t = (a + .5) / arches; x, z = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
        ax = "x" if abs(uz) > .7 else "z"
        g.torus((x, y - L / arches / 2, z), L / arches / 2, .9, bricks(a), axis=ax)
    if lamps:
        for i in range(0, 9):
            t = i / 8; x, z = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
            lamp(g, x + uz * w / 2, y + .5, z - ux * w / 2, 2.4, phase=t)

def mech_tree(g, x, y, z, h=10, seed=0):
    r = np.random.default_rng(abs(int(seed)))
    pts = [(x, y, z, 1.0), (x + r.uniform(-1, 1), y + h * .5, z + r.uniform(-1, 1), .7), (x + r.uniform(-1.5, 1.5), y + h, z + r.uniform(-1.5, 1.5), .45)]
    g.tube(pts, brass_worn(seed), mat=BRASS)
    for k in range(5):
        ang = r.uniform(0, 6.28); L = r.uniform(3, 5); yy = y + h * r.uniform(.5, .95)
        ex, ez = x + L * math.cos(ang), z + L * math.sin(ang)
        g.tube([(x, yy, z, .35), (ex, yy + 1.5, ez, .2)], COPPER, mat=METAL)
        g.ell((ex, yy + 2.2, ez), (2.2, 1.6, 2.2), lambda X, Y, Z: mixc(VERDI, hexc("#c07a3a"), fbm(X * .5, Z * .5, 2, seed, Y * .5)), mat=FOLIAGE)
        if k % 2 == 0: g.box((ex, yy + .9, ez), (.6, .6, .6), LAMP, mat=GLASS, glow=.9, grp=HIGH, phase=r.uniform())
    big_gear(g, (x, y + h * .35, z + 1.1), 1.4, .4, "z", speed=.8 * (1 if seed % 2 else -1))

def waterwheel(g, c, R=6, axis="z", speed=.35):
    px, py, pz = c
    m = g.motion(SPIN_Z if axis == "z" else SPIN_X, *( (px, py) if axis == "z" else (py, pz) ), speed)
    g.torus(c, R, .5, WOOD, axis=axis, mot=m)
    g.torus(c, R * .45, .4, IRON, axis=axis, mat=METAL, mot=m)
    for k in range(12):
        a = k / 12 * 2 * math.pi
        if axis == "z":
            g.tube([(px, py, pz, .25), (px + R * math.cos(a), py + R * math.sin(a), pz, .25)], WOOD, mot=m)
            g.box((px + R * math.cos(a), py + R * math.sin(a), pz), (1.2, 1.2, 2.4), WOOD, mot=m)
        else:
            g.tube([(px, py, pz, .25), (px, py + R * math.sin(a), pz + R * math.cos(a), .25)], WOOD, mot=m)
            g.box((px, py + R * math.sin(a), pz + R * math.cos(a)), (2.4, 1.2, 1.2), WOOD, mot=m)

def water(g, R, y, color=hexc("#3a5a5a")):
    g.cyl((0, y - .4, 0), R, 1.2, lambda x, yy, z: mixc(color, color * 1.3, fbm(x * .1, z * .1, 2)), mat=WATER, jitter=.02)

def piston(g, x, y, z, h=6, r=1.0, speed=2.0, phase=0.0):
    g.cyl((x, y + h * .35, z), r, h * .7, IRON, mat=METAL)
    m = g.motion(BOB, h * .18, phase, speed)
    g.cyl((x, y + h * .85, z), r * .45, h * .6, BRASS_C, mat=BRASS, mot=m)
    g.cyl((x, y + h * 1.15, z), r * 1.1, .6, BRASS_C, mat=BRASS, mot=m)

def dome(g, x, y, z, r, slit=True):
    g.ell((x, y, z), (r, r, r), copper_patina(9), mat=METAL)
    g.put((x - r, x + r, y - r, y, z - r, z + r), lambda X, Y, Z: True, None, erase=True)
    if slit:
        g.put((x - .9, x + .9, y, y + r + 1, z - r - 1, z), lambda X, Y, Z: True, None, erase=True)
    g.cyl((x, y - 2, z), r, 4, noisy(hexc("#8a7a6a"), hexc("#6a5a4a"), .2))
    g.tube([(x, y + r * .3, z, 1.0), (x, y + r * 1.3, z - r * .9, .7)], BRASS_C, mat=BRASS)

def orrery(g, c, n=5):
    cx, cy, cz = c
    g.ell(c, (2.2, 2.2, 2.2), LAMP, mat=GLASS, glow=1.0, grp=BASS)
    g.cyl((cx, cy - 6, cz), .5, 10, BRASS_C, mat=BRASS)
    for k in range(n):
        R = 4 + k * 3.2; sp = .5 / (1 + k * .6)
        m = g.motion(SPIN_Y, cx, cz, sp * (1 if k % 2 == 0 else -1))
        g.tube([(cx, cy - .8 - k * .3, cz, .15), (cx + R, cy - .8 - k * .3, cz, .15)], BRASS_C, mat=BRASS, mot=m)
        pc = [hexc("#c8563a"), hexc("#6a8ac8"), hexc("#d8b070"), hexc("#7ac0a0"), hexc("#b07ad0")][k % 5]
        g.ell((cx + R, cy - .8 - k * .3, cz), (.8 + k * .15,) * 3, pc, mat=METAL, mot=m, glow=.25, grp=HIGH, phase=k / n)
        g.torus((cx, cy - .8 - k * .3, cz), R, .06, BRASS_C, mat=BRASS)

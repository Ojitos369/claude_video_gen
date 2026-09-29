# Deterministic voxel generator (numpy, dense grid) + finalize (culling, smooth normals, AO, sky visibility, baked local light,
# anti-step offset, transition ordering, packing). Coordinates are world units; y is up; scenes are dioramas centred at the origin.
import math
import numpy as np
from scipy.ndimage import uniform_filter

# materials
SOLID, WATER, FOLIAGE, GLASS, STEAM, LAVA, METAL, BRASS = 1, 2, 3, 4, 5, 6, 7, 8
# light groups
BASS, MID, HIGH, CHASE = 0, 1, 2, 3
# motion types (per voxel: type, p1, p2, speed)
STATIC, SPIN_Y, SPIN_Z, SPIN_X, BOB = 0, 1, 2, 3, 4

def hexc(h):
    h = h.lstrip("#"); return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)

# ---------------------------------------------------------------- noise (vectorised value noise)
def _hash(ix, iy, iz, seed):
    h = (ix * 374761393 + iy * 668265263 + iz * 2147483647 + seed * 144269504) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0

def vn(x, z, seed=0, y=None):
    """Value noise 0..1 (2D, or 3D when y is given)."""
    x = np.asarray(x, np.float64); z = np.asarray(z, np.float64)
    y = np.zeros_like(x) if y is None else np.asarray(y, np.float64)
    ix, iy, iz = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64), np.floor(z).astype(np.int64)
    fx, fy, fz = x - ix, y - iy, z - iz
    sx, sy, sz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
    out = 0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (sx if dx else 1 - sx) * (sy if dy else 1 - sy) * (sz if dz else 1 - sz)
                out = out + w * _hash(ix + dx, iy + dy, iz + dz, seed)
    return out

def fbm(x, z, oct=4, seed=0, y=None):
    a, f, s, n = 1.0, 1.0, 0.0, 0.0
    for o in range(oct):
        s = s + a * vn(x * f, z * f, seed + o * 17, None if y is None else y * f); n += a; a *= 0.5; f *= 2.03
    return s / n

def ridge(x, z, oct=4, seed=0):
    return 1 - np.abs(fbm(x, z, oct, seed) * 2 - 1)

# ---------------------------------------------------------------- grid
class Grid:
    def __init__(self, R=64.0, ymin=-24.0, ymax=72.0, vs=0.4):
        self.R, self.vs = R, vs
        self.nx = self.nz = int(round(2 * R / vs)); self.ny = int(round((ymax - ymin) / vs))
        self.o = np.array([-R, ymin, -R], np.float32)
        shp = (self.nx, self.ny, self.nz)
        self.mat = np.zeros(shp, np.uint8); self.col = np.zeros(shp + (3,), np.uint8)
        self.glow = np.zeros(shp, np.uint8); self.grp = np.zeros(shp, np.uint8); self.phase = np.zeros(shp, np.uint8)
        self.mot = np.zeros(shp, np.uint16); self.motions = [(STATIC, 0, 0, 0)]

    def motion(self, kind, p1=0.0, p2=0.0, speed=0.0):
        self.motions.append((kind, p1, p2, speed)); return len(self.motions) - 1

    def _box(self, x0, x1, y0, y1, z0, z1):
        vs, o = self.vs, self.o
        i0 = max(0, int(math.floor((x0 - o[0]) / vs))); i1 = min(self.nx, int(math.ceil((x1 - o[0]) / vs)) + 1)
        j0 = max(0, int(math.floor((y0 - o[1]) / vs))); j1 = min(self.ny, int(math.ceil((y1 - o[1]) / vs)) + 1)
        k0 = max(0, int(math.floor((z0 - o[2]) / vs))); k1 = min(self.nz, int(math.ceil((z1 - o[2]) / vs)) + 1)
        if i1 <= i0 or j1 <= j0 or k1 <= k0: return None
        X = (o[0] + (np.arange(i0, i1) + 0.5) * vs)[:, None, None]
        Y = (o[1] + (np.arange(j0, j1) + 0.5) * vs)[None, :, None]
        Z = (o[2] + (np.arange(k0, k1) + 0.5) * vs)[None, None, :]
        return (slice(i0, i1), slice(j0, j1), slice(k0, k1)), X, Y, Z

    def put(self, bbox, maskfn, color, mat=SOLID, glow=0.0, grp=BASS, phase=0.0, mot=0, jitter=0.07, erase=False):
        """Paint every cell of bbox (x0,x1,y0,y1,z0,z1) where maskfn(X,Y,Z) is true.
        color / glow / phase may be callables f(x, y, z) evaluated only on the painted cells (1-D arrays)."""
        b = self._box(*bbox)
        if b is None: return
        sl, X, Y, Z = b
        m = np.broadcast_to(maskfn(X, Y, Z), (X.shape[0], Y.shape[1], Z.shape[2]))
        idx = np.nonzero(m)
        if len(idx[0]) == 0: return
        gi = (idx[0] + sl[0].start, idx[1] + sl[1].start, idx[2] + sl[2].start)
        if erase:
            self.mat[gi] = 0; return
        x, y, z = X[idx[0], 0, 0], Y[0, idx[1], 0], Z[0, 0, idx[2]]
        c = color(x, y, z) if callable(color) else np.broadcast_to(np.asarray(color, np.float32), (len(x), 3))
        if jitter:
            j = (_hash(gi[0], gi[1], gi[2], 7) - 0.5) * 2 * jitter
            c = c * (1 + j)[:, None]
        self.col[gi] = np.clip(c * 255, 0, 255).astype(np.uint8)
        self.mat[gi] = mat
        g = glow(x, y, z) if callable(glow) else glow
        self.glow[gi] = np.clip(np.asarray(g) * 255, 0, 255).astype(np.uint8)
        self.grp[gi] = grp
        ph = phase(x, y, z) if callable(phase) else phase
        self.phase[gi] = np.clip(np.asarray(ph) * 255, 0, 255).astype(np.uint8)
        self.mot[gi] = mot

    # ------------------------------------------------------------ primitives
    def box(self, c, size, color, **k):
        (cx, cy, cz), (sx, sy, sz) = c, size
        self.put((cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, cz - sz / 2, cz + sz / 2), lambda X, Y, Z: True, color, **k)

    def cyl(self, c, r, h, color, axis="y", shell=0.0, **k):
        """Cylinder centred at c, radius r, length h along axis (x|y|z); shell>0 makes it hollow."""
        cx, cy, cz = c; e = [r, r, r]; e["xyz".index(axis)] = h / 2
        def m(X, Y, Z):
            a, b = {"y": (X - cx, Z - cz), "x": (Y - cy, Z - cz), "z": (X - cx, Y - cy)}[axis]
            d = a * a + b * b
            return (d <= r * r) & ((d >= (r - shell) ** 2) if shell else True)
        self.put((cx - e[0], cx + e[0], cy - e[1], cy + e[1], cz - e[2], cz + e[2]), m, color, **k)

    def cone(self, base, r, h, color, r2=0.0, **k):
        bx, by, bz = base
        def m(X, Y, Z):
            u = np.clip((Y - by) / h, 0, 1); rr = r + (r2 - r) * u
            return ((X - bx) ** 2 + (Z - bz) ** 2 <= rr * rr) & (Y >= by) & (Y <= by + h)
        R = max(r, r2); self.put((bx - R, bx + R, by, by + h, bz - R, bz + R), m, color, **k)

    def ell(self, c, rad, color, **k):
        (cx, cy, cz), (rx, ry, rz) = c, rad
        self.put((cx - rx, cx + rx, cy - ry, cy + ry, cz - rz, cz + rz),
                 lambda X, Y, Z: ((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2 + ((Z - cz) / rz) ** 2 <= 1, color, **k)

    def torus(self, c, R, r, color, axis="y", **k):
        cx, cy, cz = c; e = [R + r] * 3; e["xyz".index(axis)] = r
        def m(X, Y, Z):
            a, b, h = {"y": (X - cx, Z - cz, Y - cy), "x": (Y - cy, Z - cz, X - cx), "z": (X - cx, Y - cy, Z - cz)}[axis]
            q = np.sqrt(a * a + b * b) - R
            return q * q + h * h <= r * r
        self.put((cx - e[0], cx + e[0], cy - e[1], cy + e[1], cz - e[2], cz + e[2]), m, color, **k)

    def gear(self, c, R, th, color, axis="y", teeth=16, tooth=None, hub=None, spokes=6, **k):
        """Toothed gear: rim + teeth, hub and spokes, thickness th along axis."""
        cx, cy, cz = c; tooth = tooth or R * 0.14; hub = hub or R * 0.18
        e = [R + tooth] * 3; e["xyz".index(axis)] = th / 2
        def m(X, Y, Z):
            a, b = {"y": (X - cx, Z - cz), "x": (Y - cy, Z - cz), "z": (X - cx, Y - cy)}[axis]
            r = np.sqrt(a * a + b * b); ang = np.arctan2(b, a)
            teeth_m = (r <= R + tooth) & (r > R - 0.1) & (np.cos(ang * teeth) > 0.2)
            rim = (r <= R) & (r >= R * 0.78)
            hubm = r <= hub
            sp = (np.abs(np.sin((ang) * spokes / 2)) < (0.9 / np.maximum(r, 0.5))) & (r < R)
            return teeth_m | rim | hubm | sp
        self.put((cx - e[0], cx + e[0], cy - e[1], cy + e[1], cz - e[2], cz + e[2]), m, color, **k)

    def tube(self, pts, color, **k):
        """Capsule chain through [(x, y, z, r), ...]."""
        for (x0, y0, z0, r0), (x1, y1, z1, r1) in zip(pts, pts[1:]):
            R = max(r0, r1)
            d = np.array([x1 - x0, y1 - y0, z1 - z0]); L2 = max(float(d @ d), 1e-9)
            def m(X, Y, Z, x0=x0, y0=y0, z0=z0, r0=r0, r1=r1, d=d, L2=L2):
                u = np.clip(((X - x0) * d[0] + (Y - y0) * d[1] + (Z - z0) * d[2]) / L2, 0, 1)
                px, py, pz = X - (x0 + u * d[0]), Y - (y0 + u * d[1]), Z - (z0 + u * d[2])
                rr = r0 + (r1 - r0) * u
                return px * px + py * py + pz * pz <= rr * rr
            self.put((min(x0, x1) - R, max(x0, x1) + R, min(y0, y1) - R, max(y0, y1) + R, min(z0, z1) - R, max(z0, z1) + R), m, color, **k)

    def terrain(self, H, paint, R=None, base=-20.0, **k):
        """Height field: H(x, z) -> height; every column is filled from its lowest neighbour up to its height.
        paint(x, y, z, top) -> colours (top = height at that column), plus optional mat/glow via k."""
        R = R or self.R
        xs = self.o[0] + (np.arange(self.nx) + 0.5) * self.vs; zs = self.o[2] + (np.arange(self.nz) + 0.5) * self.vs
        X2, Z2 = np.meshgrid(xs, zs, indexing="ij")
        h = H(X2, Z2)
        h = np.where(X2 ** 2 + Z2 ** 2 <= R * R, h, -1e9)
        lo = np.minimum.reduce([h, np.roll(h, 1, 0), np.roll(h, -1, 0), np.roll(h, 1, 1), np.roll(h, -1, 1)])
        lo = np.maximum(np.minimum(lo, h - self.vs), base)
        ys = self.o[1] + (np.arange(self.ny) + 0.5) * self.vs
        for j, y in enumerate(ys):
            m = (y <= h) & (y >= lo - self.vs)
            if not m.any(): continue
            ii, kk = np.nonzero(m)
            x, z = xs[ii], zs[kk]
            c = paint(x, np.full_like(x, y), z, h[ii, kk])
            jit = (_hash(ii, np.full_like(ii, j), kk, 3) - 0.5) * 2 * k.get("jitter", 0.06)
            self.col[ii, j, kk] = np.clip(c * (1 + jit)[:, None] * 255, 0, 255).astype(np.uint8)
            self.mat[ii, j, kk] = k.get("mat", SOLID)
            self.glow[ii, j, kk] = 0; self.mot[ii, j, kk] = 0

# ---------------------------------------------------------------- finalize
def finalize(g, N=600_000, seed=0):
    occ = g.mat > 0
    nb6 = np.zeros_like(occ)
    p = np.pad(occ, 1)
    full = p[2:, 1:-1, 1:-1] & p[:-2, 1:-1, 1:-1] & p[1:-1, 2:, 1:-1] & p[1:-1, :-2, 1:-1] & p[1:-1, 1:-1, 2:] & p[1:-1, 1:-1, :-2]
    moving = g.mot > 0
    vis = occ & (~full | moving)
    ii, jj, kk = np.nonzero(vis)
    wx = g.o[0] + (ii + 0.5) * g.vs; wy = g.o[1] + (jj + 0.5) * g.vs; wz = g.o[2] + (kk + 0.5) * g.vs
    if len(ii) > N:   # budget: drop the farthest from the centre first
        keep = np.argsort(wx ** 2 + wz ** 2)[:N]
        ii, jj, kk, wx, wy, wz = ii[keep], jj[keep], kk[keep], wx[keep], wy[keep], wz[keep]
    n = len(ii)
    occf = occ.astype(np.float32)
    # smooth normal: gradient of the 5x5x5-blurred occupancy
    bl = uniform_filter(occf, 5, mode="constant")
    def at(a, di=0, dj=0, dk=0):
        return a[np.clip(ii + di, 0, g.nx - 1), np.clip(jj + dj, 0, g.ny - 1), np.clip(kk + dk, 0, g.nz - 1)]
    nx_ = at(bl, -1) - at(bl, 1); ny_ = at(bl, 0, -1) - at(bl, 0, 1); nz_ = at(bl, 0, 0, -1) - at(bl, 0, 0, 1)
    nl = np.sqrt(nx_ ** 2 + ny_ ** 2 + nz_ ** 2) + 1e-6
    nrm = np.stack([nx_ / nl, ny_ / nl, nz_ / nl], 1)
    nrm[nl < 1e-3] = (0, 1, 0)
    del bl
    # ambient occlusion: occupied fraction of the 26 neighbours
    nb = uniform_filter(occf, 3, mode="constant") * 27 - 1
    nbv = at(nb); del nb
    ao = 1 - np.clip(nbv / 26, 0, 1)
    offset = np.clip((nbv / 26 - 0.654) * 2.2, -0.6, 0.6)   # anti-step, along the normal (voxel units)
    # sky visibility: 5 rays (up + 4 diagonals) of up to 14 cells
    blocked = np.zeros(n, np.float32)
    for dx, dz in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]:
        hit = np.zeros(n, bool)
        for s in range(1, 15):
            i2, j2, k2 = ii + dx * s, jj + s, kk + dz * s
            ok = (i2 >= 0) & (i2 < g.nx) & (j2 < g.ny) & (k2 >= 0) & (k2 < g.nz)
            h = np.zeros(n, bool)
            h[ok] = occ[i2[ok], j2[ok], k2[ok]]
            hit |= h
        blocked += hit
    sky = 1 - blocked / 5
    del occf
    # baked local light: emissive colour summed on a 4-cell coarse grid, blurred
    c = 4
    em = (g.col.astype(np.float32) / 255) ** 2.2 * (g.glow.astype(np.float32)[..., None] / 255)
    sx, sy, sz = g.nx // c, g.ny // c, g.nz // c
    em = em[:sx * c, :sy * c, :sz * c].reshape(sx, c, sy, c, sz, c, 3).sum((1, 3, 5))
    for _ in range(2):
        em = uniform_filter(em, (5, 5, 5, 1), mode="constant")
    lit = em[np.clip(ii // c, 0, sx - 1), np.clip(jj // c, 0, sy - 1), np.clip(kk // c, 0, sz - 1)] * 1.5
    lit = lit / (lit + 1.2)
    del em
    col = g.col[ii, jj, kk]; mat = g.mat[ii, jj, kk]; glow = g.glow[ii, jj, kk]; grp = g.grp[ii, jj, kk]; ph = g.phase[ii, jj, kk]
    mt = np.array(g.motions, np.float32)[g.mot[ii, jj, kk]]
    # transition order: height band, then angle around the centre (voxel i of scene A flies to voxel i of scene B)
    band = np.clip(((wy - g.o[1]) / (g.ny * g.vs) * 8).astype(int), 0, 7)
    ang = (np.arctan2(wz, wx) / (2 * np.pi) + 0.5)
    order = np.argsort(band * 1000 + (ang * 999).astype(int), kind="stable")
    pack = {
        "pos": np.concatenate([np.stack([wx, wy, wz], 1), offset[:, None]], 1).astype(np.float32)[order],
        "col": np.concatenate([col, (ao * 255)[:, None]], 1).astype(np.uint8)[order],
        "nrm": np.concatenate([(nrm * 0.5 + 0.5) * 255, mat[:, None].astype(np.float32) * 10], 1).clip(0, 255).astype(np.uint8)[order],
        "misc": np.stack([glow, grp * 60, ph, np.full(n, 255)], 1).astype(np.uint8)[order],   # w=255 visible
        "lit": np.concatenate([lit * 255, (sky * 255)[:, None]], 1).clip(0, 255).astype(np.uint8)[order],
        "mot": mt.astype(np.float16)[order],
    }
    return pack, n

def pad(pack, n, N, R, seed=0):
    """Pad a packed scene to N instances with hidden voxels parked under the diorama (they emerge in transitions)."""
    if n >= N: return {k: v[:N] for k, v in pack.items()}
    r = np.random.default_rng(seed); m = N - n
    a = r.uniform(0, 2 * np.pi, m); d = np.sqrt(r.uniform(0, 1, m)) * R
    extra = {
        "pos": np.stack([d * np.cos(a), np.full(m, -40.0), d * np.sin(a), np.zeros(m)], 1).astype(np.float32),
        "col": np.full((m, 4), 128, np.uint8), "nrm": np.tile(np.array([128, 255, 128, 10], np.uint8), (m, 1)),
        "misc": np.zeros((m, 4), np.uint8), "lit": np.zeros((m, 4), np.uint8), "mot": np.zeros((m, 4), np.float16),
    }
    # interleave hidden voxels evenly so every height band / angle has some
    idx = np.arange(m) * N // m
    out = {}
    mask = np.zeros(N, bool); mask[idx] = True
    for k in pack:
        arr = np.empty((N,) + pack[k].shape[1:], pack[k].dtype)
        arr[mask] = extra[k]; arr[~mask] = pack[k]
        out[k] = arr
    return out

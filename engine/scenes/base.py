# Drawing helpers shared by every scene module. Scenes draw on a BW x BH canvas (half the output resolution).
import math
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BW, BH = 540, 960
# named palette; a project can override any of these in config.json -> "palette"
PLUM, DEEP, ROSE, PINK = (26, 15, 46), (58, 22, 82), (255, 90, 160), (255, 170, 205)
LILAC, CREAM, GOLD, SKY, HOT = (182, 156, 255), (255, 244, 230), (255, 210, 122), (140, 180, 255), (255, 60, 140)

@lru_cache(maxsize=64)
def grad(c1, c2, c3=None):
    y = np.linspace(0, 1, BH)[:, None, None]
    a, b = np.array(c1, float), np.array(c2, float)
    if c3 is None: g = a + (b - a) * y
    else:
        c = np.array(c3, float)
        g = np.where(y < 0.5, a + (b - a) * (y * 2), b + (c - b) * ((y - 0.5) * 2))
    return np.broadcast_to(g, (BH, BW, 3)).astype(np.uint8).copy()

def mix(c1, c2, k):
    return tuple(int(a + (b - a) * k) for a, b in zip(c1, c2))

def rgba(c, a):
    return (c[0], c[1], c[2], int(max(0, min(255, a))))

def rot(pts, ang, cx, cy):
    ca, sa = math.cos(ang), math.sin(ang)
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]

def heart_pts(cx, cy, s, ang=0.0):
    pts = []
    for k in range(40):
        a = k / 40 * 2 * math.pi
        x = 16 * math.sin(a) ** 3
        y = -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a))
        pts.append((x * s / 16, y * s / 16))
    return rot(pts, ang, cx, cy)

def star_pts(cx, cy, r, n=5, inner=0.45, ang=0.0):
    pts = []
    for k in range(2 * n):
        rr = r if k % 2 == 0 else r * inner
        a = ang + k * math.pi / n - math.pi / 2
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts

def sparkle_pts(cx, cy, r, ang=0.0):
    return star_pts(cx, cy, r, 4, 0.18, ang)

def petal_pts(cx, cy, length, width, ang):
    pts = [(0, 0)]
    for k in range(1, 12):
        u = k / 12
        pts.append((u * length, math.sin(u * math.pi) * width))
    pts.append((length, 0))
    for k in range(11, 0, -1):
        u = k / 12
        pts.append((u * length, -math.sin(u * math.pi) * width))
    return rot(pts, ang, cx, cy)

def flower(d, g, cx, cy, r, ang, col, center=GOLD, n=5, a=230):
    for k in range(n):
        pp = petal_pts(cx, cy, r, r * 0.42, ang + k * 2 * math.pi / n)
        d.polygon(pp, fill=rgba(col, a))
        if g is not None: g.polygon(pp, fill=rgba(col, 120))
    d.ellipse([cx - r * .22, cy - r * .22, cx + r * .22, cy + r * .22], fill=rgba(center, 255))

class Ctx:
    def __init__(self, base):
        self.img = Image.fromarray(base)
        self.d = ImageDraw.Draw(self.img, "RGBA")
        self.gimg = Image.new("RGB", (BW, BH))
        self.g = ImageDraw.Draw(self.gimg, "RGBA")
    def finish(self, glow_r=7, glow_k=1.0):
        gl = np.asarray(self.gimg.filter(ImageFilter.GaussianBlur(glow_r)), np.float32) * glow_k
        a = np.asarray(self.img, np.float32)
        return 255 - (255 - a) * (255 - np.minimum(gl, 255)) / 255   # screen blend

def R(seed):
    return np.random.default_rng(seed)


# ---------------------------------------------------------------- sprites (character images)
@lru_cache(maxsize=64)
def cutout(path, size=360, tol=60, hue=0.0, sat=1.0, val=1.0):
    """RGBA sprite from an image with a flat background: flood-fill from the border to transparent, crop, fit in size px.
    hue (0..1 shift) / sat / val give colour variants of the same character."""
    im = Image.open(path).convert("RGB")
    im.thumbnail((700, 700))
    key = (255, 0, 255)
    work = im.copy()
    w, h = work.size
    for x, y in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        if work.getpixel((x, y)) != key: ImageDraw.floodfill(work, (x, y), key, thresh=tol)
    a = np.asarray(work)
    alpha = Image.fromarray(np.where((a == key).all(2), 0, 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1))
    if hue or sat != 1 or val != 1:
        hsv = np.asarray(im.convert("HSV")).astype(np.float32)
        hsv[..., 0] = (hsv[..., 0] + hue * 255) % 255
        hsv[..., 1] = np.clip(hsv[..., 1] * sat, 0, 255); hsv[..., 2] = np.clip(hsv[..., 2] * val, 0, 255)
        im = Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB")
    sp = im.convert("RGBA"); sp.putalpha(alpha)
    sp = sp.crop(alpha.getbbox())
    sp.thumbnail((size, size), Image.LANCZOS)
    return sp

@lru_cache(maxsize=64)
def silhouette(sp_key, color, blur):
    sp = cutout(*sp_key)
    sil = Image.new("RGBA", sp.size, color + (0,))
    sil.putalpha(sp.getchannel("A"))
    pad = int(blur * 3)
    out = Image.new("RGBA", (sp.width + 2 * pad, sp.height + 2 * pad))
    out.paste(sil, (pad, pad))
    return out.filter(ImageFilter.GaussianBlur(blur)), pad

def put(ctx, sp_key, cx, cy, h, ang=0.0, alpha=1.0, flip=False, glow=None, glow_k=1.0):
    """Paste a sprite (cutout args tuple) centred at (cx, cy) with height h px, rotation (deg), optional coloured glow."""
    sp = cutout(*sp_key)
    k = h / sp.height
    if glow is not None:
        gl, pad = silhouette(sp_key, glow, 10)
        g = gl.resize((max(1, int(gl.width * k)), max(1, int(gl.height * k))))
        if flip: g = g.transpose(Image.FLIP_LEFT_RIGHT)
        if ang: g = g.rotate(ang, expand=True, resample=Image.BILINEAR)
        ga = np.asarray(g.getchannel("A"), np.float32) * glow_k * alpha
        col = Image.new("RGB", g.size, glow)
        ctx.gimg.paste(col, (int(cx - g.width / 2), int(cy - g.height / 2)), Image.fromarray(np.clip(ga, 0, 255).astype(np.uint8)))
    s = sp.resize((max(1, int(sp.width * k)), max(1, int(sp.height * k))), Image.BILINEAR)
    if flip: s = s.transpose(Image.FLIP_LEFT_RIGHT)
    if ang: s = s.rotate(ang, expand=True, resample=Image.BILINEAR)
    if alpha < 1:
        a = s.getchannel("A").point(lambda v: int(v * alpha)); s.putalpha(a)
    ctx.img.paste(s, (int(cx - s.width / 2), int(cy - s.height / 2)), s)

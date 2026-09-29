# Motif library v1 (first used in projects/crazier). Signature: sc_<name>(t, lt, v, p, e, bt, blk)
#   t: song time, lt: time since the cut, v: cut index inside the block (variant), p: beat pulse 0..1,
#   e: energy 0..1, bt: time since the storyboard block started, blk: the storyboard block dict (custom params).
# Coordinates are designed for a vertical 540x960 canvas.
import math
import numpy as np
from functools import lru_cache
from .base import *
from ..timing import since_beat, en
from .. import timing

# ---------------------------------------------------------------- scenes (t: global time, lt: time in cut, v: variant, p: pulse, e: energy)
def sc_dream(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((20, 12, 48), (58, 26, 96), (120, 60, 130)))
    r = R(11 + v)
    for k in range(110):
        x, y, ph = r.uniform(0, BW), r.uniform(0, BH * 0.8), r.uniform(0, 6.3)
        b = 0.5 + 0.5 * math.sin(t * 2.5 + ph)
        s = 1 + (k % 3 == 0)
        c.d.ellipse([x - s, y - s, x + s, y + s], fill=rgba(CREAM, 90 + 160 * b))
        if k % 9 == 0: c.g.polygon(sparkle_pts(x, y, 7 + 5 * b), fill=rgba(CREAM, 200 * b))
    for k in range(14):
        x = (r.uniform(0, BW) + 9 * lt * (1 if k % 2 else -1)) % BW
        y = (r.uniform(0, BH) - 14 * t) % (BH + 120) - 60
        rr = r.uniform(18, 60)
        col = [PINK, LILAC, SKY][k % 3]
        c.g.ellipse([x - rr, y - rr, x + rr, y + rr], fill=rgba(col, 70 + 60 * p))
    mx = 400 if v % 2 == 0 else 140
    c.d.ellipse([mx - 46, 150, mx + 46, 242], fill=rgba(CREAM, 240))
    c.d.ellipse([mx - 26, 136, mx + 60, 226], fill=(34, 18, 66, 255))
    c.g.ellipse([mx - 60, 136, mx + 60, 256], fill=rgba(CREAM, 90))
    return c.finish(9)

def sc_world(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((24, 10, 40), (80, 24, 90), (150, 40, 110)))
    r = R(23 + v)
    cx, cy = BW / 2 + (40 if v % 2 else -40), BH / 2
    speed = 0.4 + 1.6 * e
    for k in range(22):
        rr = 40 + k * 22
        a0 = r.uniform(0, 6.3) + t * speed * (1 if k % 2 else -1) * (0.3 + k * 0.02)
        col = [LILAC, PINK, ROSE][k % 3]
        c.d.arc([cx - rr, cy - rr, cx + rr, cy + rr], math.degrees(a0), math.degrees(a0) + 200 + 60 * math.sin(k), fill=rgba(col, 90 + 100 * p), width=2)
        x, y = cx + rr * math.cos(a0), cy + rr * math.sin(a0)
        c.g.ellipse([x - 5, y - 5, x + 5, y + 5], fill=rgba(col, 255))
    # watching eyes
    for k in range(9):
        x, y = r.uniform(50, BW - 50), r.uniform(70, BH - 70)
        if abs(y - BH / 2) < 150: y += 300 if y > BH / 2 else -300
        blink = abs(math.sin(t * 0.9 + k * 1.7)) ** 0.15
        w, hh = 34, 16 * blink
        c.d.ellipse([x - w, y - hh, x + w, y + hh], fill=rgba(CREAM, 220), outline=rgba(PLUM, 255), width=2)
        lx = x + 12 * math.sin(t * 1.3 + k)
        c.d.ellipse([lx - 8, y - min(8, hh), lx + 8, y + min(8, hh)], fill=rgba(DEEP, 255))
        c.g.ellipse([x - w - 6, y - hh - 6, x + w + 6, y + hh + 6], fill=rgba(PINK, 60))
    return c.finish(8)

def sc_screen(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((30, 14, 56), (90, 40, 120), (40, 16, 60)))
    r = R(37 + v)
    ox = [-20, 30, 0, -40][v % 4]
    x0, y0, x1, y1 = 120 + ox, 170, 420 + ox, 790
    c.g.rounded_rectangle([x0 - 16, y0 - 16, x1 + 16, y1 + 16], 50, fill=rgba(ROSE, 110 + 80 * p))
    c.d.rounded_rectangle([x0 - 10, y0 - 10, x1 + 10, y1 + 10], 46, fill=(15, 8, 25, 255))
    c.d.rounded_rectangle([x0, y0, x1, y1], 38, fill=rgba(mix(PINK, LILAC, 0.5), 255))
    scroll = (t * 45) % 150
    for k in range(-1, 6):
        yy = y0 + 20 + k * 150 - scroll
        if yy + 130 < y0 + 10 or yy > y1 - 10: continue
        a0, a1 = max(yy, y0 + 12), min(yy + 130, y1 - 12)
        if a1 - a0 < 40: continue
        c.d.rounded_rectangle([x0 + 18, a0, x1 - 18, a1], 18, fill=rgba(CREAM, 235))
        hx = x0 + 60
        if a0 < yy + 30 < a1 - 20:   # smiling girl avatar
            c.d.ellipse([hx - 22, yy + 12, hx + 22, yy + 56], fill=rgba(ROSE, 255))
            c.d.arc([hx - 11, yy + 26, hx + 11, yy + 46], 20, 160, fill=CREAM, width=3)
            for q in range(3):
                bx = hx + 45 + q * 0
                if yy + 24 + q * 22 < a1 - 6:
                    c.d.rounded_rectangle([bx, yy + 20 + q * 22, x1 - 40 - q * 40, yy + 30 + q * 22], 5, fill=rgba(LILAC, 200))
    for k in range(18):
        ph = r.uniform(0, 1); spd = r.uniform(0.25, 0.5)
        u = (lt * spd + ph) % 1
        x = (x1 if k % 2 else x0) + (1 if k % 2 else -1) * (20 + 50 * math.sin(u * 7 + k))
        y = y1 - u * (y1 - y0 + 200)
        s = 12 + 8 * r.uniform() + 6 * p
        pts = heart_pts(x, y, s)
        c.d.polygon(pts, fill=rgba(HOT, 255 * (1 - u)))
        c.g.polygon(pts, fill=rgba(ROSE, 220 * (1 - u)))
    return c.finish(10)

def sc_diary(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((255, 240, 228), (250, 214, 226)))
    r = R(51 + v)
    for y in range(60, BH, 38):
        c.d.line([(0, y), (BW, y)], fill=(170, 170, 230, 150), width=2)
    mx = 70 if v % 2 == 0 else BW - 70
    c.d.line([(mx, 0), (mx, BH)], fill=(240, 110, 150, 200), width=3)
    for k in range(10):    # doodles pop in on beats
        x, y = r.uniform(40, BW - 40), r.uniform(60, BH - 60)
        if abs(y - BH / 2) < 170: continue
        if k % 3 == 0: pts = heart_pts(x, y, 20, r.uniform(-.4, .4))
        else: pts = star_pts(x, y, 22, 5, 0.45, r.uniform(0, 1))
        s = 1 + 0.15 * p
        pts = [(x + (px - x) * s, y + (py - y) * s) for px, py in pts]
        c.d.line(pts + [pts[0]], fill=rgba([ROSE, (120, 100, 220), GOLD][k % 3], 230), width=3)
    # handwriting scribble revealed over time
    for row in range(3):
        y = 120 + row * 38 - 14 if v % 2 == 0 else BH - 200 + row * 38 - 14
        n = int(min(1, lt / 1.6) * 60)
        pts = [(110 + i * 5.5, y + 8 * math.sin(i * 0.9 + row) + 4 * math.sin(i * 2.3)) for i in range(n)]
        if len(pts) > 1: c.d.line(pts, fill=(80, 50, 120, 220), width=3)
    # film strip (movie cliché)
    fy = [650, 250, 720, 300][v % 4]
    c.d.rectangle([0, fy, BW, fy + 110], fill=(30, 18, 40, 240))
    off = (t * 70) % 130
    for k in range(-1, 6):
        x = k * 130 - off
        c.d.rounded_rectangle([x + 12, fy + 22, x + 118, fy + 88], 6, fill=rgba(mix(PINK, SKY, (k % 3) / 2), 255))
        for hole in range(4):
            hx = x + 10 + hole * 32
            c.d.rectangle([hx, fy + 6, hx + 14, fy + 14], fill=CREAM)
            c.d.rectangle([hx, fy + 96, hx + 14, fy + 104], fill=CREAM)
        c.g.rounded_rectangle([x + 12, fy + 22, x + 118, fy + 88], 6, fill=rgba(PINK, 60 + 100 * p))
    return c.finish(8, 0.6)

def sc_box(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((16, 10, 34), (40, 20, 70), (20, 12, 40)))
    s, gap = 78, 22
    cols, rows = 5, 9
    ox = (BW - (cols * s + (cols - 1) * gap)) / 2; oy = (BH - (rows * s + (rows - 1) * gap)) / 2
    esc = [(1, 1), (3, 7), (0, 5), (4, 2), (2, 8)][v % 5]
    for i in range(cols):
        for j in range(rows):
            x, y = ox + i * (s + gap), oy + j * (s + gap)
            if (i, j) == esc: continue
            c.d.rectangle([x, y, x + s, y + s], outline=rgba(LILAC, 110 + 120 * p), width=2)
    i, j = esc
    x, y = ox + i * (s + gap) + s / 2, oy + j * (s + gap) + s / 2
    k = min(1, lt / 1.8)
    dx, dy = (x - BW / 2), (y - BH / 2)
    n = math.hypot(dx, dy) + 1
    x += dx / n * 160 * k; y += dy / n * 160 * k - 40 * k
    sz = s / 2 * (1 + 0.3 * k + 0.12 * p)
    pts = rot([(-sz, -sz), (sz, -sz), (sz, sz), (-sz, sz)], k * 0.8, x, y)
    c.d.rectangle([ox + esc[0] * (s + gap), oy + esc[1] * (s + gap), ox + esc[0] * (s + gap) + s, oy + esc[1] * (s + gap) + s], outline=rgba(ROSE, 120), width=2)
    c.d.polygon(pts, fill=rgba(ROSE, 240))
    c.g.polygon(pts, fill=rgba(PINK, 255))
    for q in range(12):
        a = q / 12 * 6.28 + t
        c.g.ellipse([x + 70 * k * math.cos(a) - 3, y + 70 * k * math.sin(a) - 3, x + 70 * k * math.cos(a) + 3, y + 70 * k * math.sin(a) + 3], fill=rgba(GOLD, 255))
    return c.finish(12)

def sc_chorus(t, lt, v, p, e, bt=0.0, blk=None):
    pals = [((255, 80, 150), (140, 40, 150), (40, 14, 70)), ((255, 150, 100), (220, 60, 140), (60, 20, 90)),
            ((190, 120, 255), (230, 70, 160), (40, 14, 70)), ((255, 110, 170), (110, 60, 200), (30, 14, 60))]
    c = Ctx(grad(*pals[v % 4]))
    cx, cy = BW / 2, BH / 2
    ang = t * 0.35 * (1 if v % 2 else -1)
    for k in range(14):
        a0 = ang + k * 2 * math.pi / 14
        pts = [(cx, cy), (cx + 900 * math.cos(a0), cy + 900 * math.sin(a0)), (cx + 900 * math.cos(a0 + 0.2), cy + 900 * math.sin(a0 + 0.2))]
        c.d.polygon(pts, fill=rgba(CREAM, 28 + 40 * p))
    r = R(71 + v)
    for k in range(7):
        a = k / 7 * 6.28 + t * 0.4
        rad = 260 + 40 * math.sin(t + k)
        x, y = cx + rad * math.cos(a) * 0.9, cy + rad * math.sin(a) * 1.35
        flower(c.d, c.g, x, y, 34 + 18 * p + 6 * math.sin(k), t * 0.8 + k, [PINK, CREAM, LILAC, GOLD][k % 4], ROSE if k % 4 == 3 else GOLD)
    sb, bi = since_beat(t)
    rb = R(1000 + bi)
    for k in range(34):     # burst of sparkles every beat
        a = rb.uniform(0, 6.28); spd = rb.uniform(250, 600)
        d = spd * sb * (1 - sb * 0.6)
        x, y = cx + d * math.cos(a), cy + d * math.sin(a) * 1.3
        al = max(0, 1 - sb / 0.55)
        c.g.polygon(sparkle_pts(x, y, 8 + 6 * al, a), fill=rgba([CREAM, GOLD, PINK][k % 3], 255 * al))
    for k in range(40):     # confetti
        x = (r.uniform(0, BW) + 30 * math.sin(t + k)) % BW
        y = (r.uniform(0, BH) + t * r.uniform(60, 140)) % BH
        a = t * 3 + k
        pts = rot([(-5, -2.5), (5, -2.5), (5, 2.5), (-5, 2.5)], a, x, y)
        c.d.polygon(pts, fill=rgba([CREAM, GOLD, LILAC, PINK][k % 4], 220))
    return c.finish(9, 1.0 + 0.4 * p)

def sc_petals(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((70, 40, 110), (190, 110, 180), (255, 190, 210)))
    r = R(81 + v)
    for k in range(45):
        x0, ph, spd = r.uniform(0, BW), r.uniform(0, 1), r.uniform(0.07, 0.14)
        u = (t * spd + ph) % 1
        x = x0 + 40 * math.sin(u * 10 + k)
        y = -30 + u * (BH + 60)
        pp = petal_pts(x, y, 22 + 8 * r.uniform(), 9, t * 1.5 + k)
        c.d.polygon(pp, fill=rgba([PINK, CREAM, (255, 140, 180)][k % 3], 220))
        if k % 4 == 0: c.g.polygon(pp, fill=rgba(PINK, 150))
    return c.finish(8)

def sc_rain(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((70, 64, 100), (48, 40, 74), (28, 22, 44)))
    r = R(91 + v)
    for k in range(9):
        x, y, rr = r.uniform(-40, BW + 40) + 12 * math.sin(t * 0.3 + k), r.uniform(20, 200), r.uniform(60, 110)
        c.d.ellipse([x - rr, y - rr * .6, x + rr, y + rr * .6], fill=(120, 110, 150, 120))
    for k in range(160):
        x0, ph = r.uniform(-60, BW + 60), r.uniform(0, 1)
        u = (t * 1.4 + ph) % 1
        y = u * (BH + 100) - 50
        x = x0 - u * 60
        c.d.line([(x, y), (x - 6, y + 26)], fill=(200, 200, 240, 130), width=2)
    for k in range(6):
        cx, ph = r.uniform(40, BW - 40), r.uniform(0, 1)
        u = (t * 0.7 + ph) % 1
        rr = 10 + 70 * u
        c.d.ellipse([cx - rr, 880 - rr * .25, cx + rr, 880 + rr * .25], outline=rgba(LILAC, 200 * (1 - u)), width=2)
    c.g.ellipse([BW / 2 - 200, 380, BW / 2 + 200, 580], fill=rgba(LILAC, 40 + 40 * p))
    return c.finish(14)

def sc_childhood(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((150, 190, 255), (210, 180, 250), (255, 200, 220)))
    r = R(101 + v)
    cx, cy = BW / 2, BH + 60
    for k, col in enumerate([(255, 120, 150), (255, 190, 120), (255, 240, 150), (150, 230, 170), (140, 190, 255), (190, 150, 255)]):
        rr = 460 - k * 26
        c.d.arc([cx - rr, cy - rr, cx + rr, cy + rr], 180, 360, fill=rgba(col, 230), width=24)
    for k in range(9):
        x, y = r.uniform(30, BW - 30), r.uniform(40, 520)
        jit = 2 * math.sin(t * 20 + k)
        pts = star_pts(x + jit, y, 18 + 5 * p, 5, 0.45, r.uniform(0, 1))
        c.d.line(pts + [pts[0]], fill=rgba([GOLD, ROSE, (255, 255, 255)][k % 3], 255), width=4)
        c.g.polygon(pts, fill=rgba(CREAM, 120))
    u = (lt / 2.2) % 1
    px = -60 + u * (BW + 120) if v % 2 == 0 else BW + 60 - u * (BW + 120)
    py = 300 - 120 * math.sin(u * math.pi)
    dirn = 1 if v % 2 == 0 else -1
    pl = [(px + 34 * dirn, py), (px - 30 * dirn, py - 16), (px - 18 * dirn, py + 2), (px - 30 * dirn, py + 16)]
    c.d.polygon(pl, fill=(255, 255, 255, 250), outline=(120, 100, 200, 255))
    for k in range(10):
        q = u - k * 0.02
        if q < 0: break
        tx = -60 + q * (BW + 120) if v % 2 == 0 else BW + 60 - q * (BW + 120)
        ty = 300 - 120 * math.sin(q * math.pi)
        c.d.ellipse([tx - 2, ty - 2, tx + 2, ty + 2], fill=(255, 255, 255, 200 - k * 18))
    return c.finish(8, 0.7)

def sc_home(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((40, 20, 70), (130, 60, 120), (255, 150, 140)))
    r = R(111 + v)
    cx, cy, s = BW / 2, 700, 140
    fade = max(0.25, 1 - lt / 3)
    col = rgba(CREAM, 255 * fade)
    c.d.line([(cx - s, cy), (cx - s, cy - s * 1.1), (cx, cy - s * 1.9), (cx + s, cy - s * 1.1), (cx + s, cy), (cx - s, cy)], fill=col, width=5)
    c.d.rectangle([cx - 30, cy - 90, cx + 30, cy], outline=col, width=4)
    c.d.rectangle([cx + 55, cy - 120, cx + 105, cy - 70], fill=rgba(GOLD, 200 * fade))
    c.g.rectangle([cx + 55, cy - 120, cx + 105, cy - 70], fill=rgba(GOLD, 200))
    for k in range(70):    # house dissolving into particles
        ph = r.uniform(0, 1)
        u = min(1, max(0, lt / 2.5 - ph * 0.5))
        sx, sy = cx + r.uniform(0, s), cy - r.uniform(0, s * 1.5)
        x, y = sx + u * r.uniform(60, 220), sy - u * r.uniform(80, 300)
        c.d.rectangle([x - 3, y - 3, x + 3, y + 3], fill=rgba([CREAM, PINK, GOLD][k % 3], 255 * (1 - u * 0.7)))
        c.g.ellipse([x - 4, y - 4, x + 4, y + 4], fill=rgba(PINK, 200 * (1 - u)))
    c.d.rectangle([0, cy, BW, BH], fill=(30, 16, 44, 255))
    return c.finish(9)

def sc_book(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((24, 12, 44), (70, 30, 90), (30, 14, 50)))
    r = R(121 + v)
    cx, cy = BW / 2, 720 if v % 2 == 0 else 250
    lp = [(cx, cy - 110), (cx - 230, cy - 140), (cx - 240, cy + 110), (cx, cy + 130)]
    rp = [(cx, cy - 110), (cx + 230, cy - 140), (cx + 240, cy + 110), (cx, cy + 130)]
    c.g.polygon(lp + rp[::-1], fill=rgba(GOLD, 120 + 80 * p))
    c.d.polygon(lp, fill=CREAM); c.d.polygon(rp, fill=(250, 236, 222))
    for k in range(7):
        y = cy - 90 + k * 28
        c.d.line([(cx - 200, y - 10 + k * 1), (cx - 30, y)], fill=(180, 160, 190, 200), width=5)
        c.d.line([(cx + 30, y), (cx + 200, y - 10 + k)], fill=(180, 160, 190, 200), width=5)
    c.d.polygon([(cx + 120, cy - 132), (cx + 150, cy - 136), (cx + 150, cy + 60), (cx + 135, cy + 45), (cx + 120, cy + 62)], fill=rgba(ROSE, 255))
    u = (lt / 1.6) % 1        # page flip
    fx = cx + 230 * math.cos(u * math.pi)
    lift = 60 * math.sin(u * math.pi)
    c.d.polygon([(cx, cy - 110), (fx, cy - 140 - lift), (fx, cy + 110 - lift * 0.6), (cx, cy + 130)], fill=(255, 250, 240, 230), outline=(200, 180, 200, 255))
    for k in range(26):
        ph, x0 = r.uniform(0, 1), r.uniform(cx - 220, cx + 220)
        q = (t * 0.35 + ph) % 1
        y = cy - 130 - q * 420
        c.g.polygon(sparkle_pts(x0 + 20 * math.sin(q * 8), y, 6 + 4 * (1 - q)), fill=rgba([GOLD, PINK, CREAM][k % 3], 255 * (1 - q)))
    return c.finish(10)

def sc_door(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((14, 8, 26), (36, 18, 60), (20, 10, 34)))
    cx, top, bot = BW / 2 + (-30 if v % 2 else 30), 260, 820
    open_k = min(1, lt / 1.5) * 0.85 + 0.15
    hw = 110 * open_k
    for k in range(9):
        a = -0.9 + k * 0.225
        pts = [(cx - hw, bot), (cx + hw, bot), (cx + 700 * math.sin(a + 0.1), bot - 900), (cx + 700 * math.sin(a), bot - 900)]
        c.d.polygon([(cx, (top + bot) / 2), (cx + 900 * math.sin(a), (top + bot) / 2 + 900 * math.cos(a) * (-1 if k % 2 else 1)), (cx + 900 * math.sin(a + 0.08), (top + bot) / 2 + 900 * math.cos(a + 0.08) * (-1 if k % 2 else 1))], fill=rgba(GOLD, 30 + 30 * p))
    c.d.rectangle([cx - 115, top, cx + 115, bot], outline=(90, 60, 110, 255), width=6)
    c.d.rectangle([cx - hw, top + 5, cx + hw, bot], fill=rgba(mix(CREAM, GOLD, 0.4), 255))
    c.g.rectangle([cx - hw - 20, top - 20, cx + hw + 20, bot + 20], fill=rgba(GOLD, 220))
    for k in range(5):    # scent swirls
        pts = []
        for i in range(60):
            q = i / 60
            x = cx + (q * 260 + 20) * (1 if k % 2 else -1) + 20 * math.sin(q * 9 + t * 2 + k)
            y = bot - 80 - k * 90 - q * 120 + 14 * math.sin(q * 12 + t * 3)
            pts.append((x, y))
        c.d.line(pts, fill=rgba(PINK, 160), width=3)
        c.g.line(pts, fill=rgba(ROSE, 200), width=6)
    return c.finish(14)

def sc_heart(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((60, 10, 50), (150, 30, 90), (40, 10, 50)))
    r = R(141 + v)
    cx, cy = BW / 2, BH / 2
    s = 190 * (1 + 0.14 * p)
    c.g.polygon(heart_pts(cx, cy + 20, s * 1.1), fill=rgba(ROSE, 255))
    c.d.polygon(heart_pts(cx, cy + 20, s), fill=rgba((230, 40, 110), 255))
    c.d.polygon(heart_pts(cx - 40, cy - 40, s * 0.25, -0.5), fill=(255, 200, 220, 110))
    ey = 800 if v % 2 == 0 else 160
    pts = []
    for i in range(0, BW + 1, 4):
        tt = t - (BW - i) / 300
        sb, _ = since_beat(tt)
        y = ey - (60 * math.exp(-((sb - 0.03) / 0.03) ** 2) - 25 * math.exp(-((sb - 0.09) / 0.03) ** 2)) * (0.6 + en(max(0, tt)))
        pts.append((i, y))
    c.d.line(pts, fill=rgba(CREAM, 240), width=3)
    c.g.line(pts, fill=rgba(PINK, 255), width=6)
    for k in range(16):
        ph, x0 = r.uniform(0, 1), r.uniform(0, BW)
        q = (t * 0.18 + ph) % 1
        hp = heart_pts(x0 + 25 * math.sin(q * 7 + k), BH - q * (BH + 60), 10 + 6 * r.uniform())
        c.d.polygon(hp, fill=rgba(PINK, 200 * math.sin(q * math.pi)))
    return c.finish(16, 0.9 + 0.5 * p)

def sc_eyes(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((16, 10, 40), (60, 36, 110), (20, 12, 44)))
    r = R(151 + v)
    for k in range(50):
        x, y, ph = r.uniform(0, BW), r.uniform(0, BH), r.uniform(0, 6.3)
        b = max(0, math.sin(t * 3 + ph)) ** 3
        sz = 5 + 14 * b + (10 * p if k % 5 == 0 else 0)
        pts = sparkle_pts(x, y, sz, 0.3 * math.sin(t + k))
        c.d.polygon(pts, fill=rgba(CREAM, 80 + 175 * b))
        c.g.polygon(pts, fill=rgba([LILAC, PINK, SKY][k % 3], 255 * b))
    bx, by = (150, 250) if v % 2 == 0 else (390, 700)
    big = 70 * (1 + 0.3 * p)
    c.d.polygon(sparkle_pts(bx, by, big, t * 0.3), fill=rgba(CREAM, 255))
    c.g.ellipse([bx - big, by - big, bx + big, by + big], fill=rgba(PINK, 200))
    for k in range(5):
        q = (k + 1) / 6
        x, y = bx + (BW - 2 * bx) * q, by + (BH - 2 * by) * q
        rr = 16 + 26 * (k % 3)
        c.d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=rgba([LILAC, PINK, GOLD][k % 3], 50), outline=rgba(CREAM, 70), width=2)
    return c.finish(10, 1.1)

@lru_cache(maxsize=4)
def grain(i):
    return R(900 + i).normal(0, 14, (BH, BW, 1)).astype(np.float32)

def sc_youth(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((255, 214, 190), (240, 140, 170), (110, 60, 130)))
    r = R(161 + v)
    for k in range(4):
        x, y = r.uniform(-60, BW + 60), r.uniform(0, BH)
        c.g.ellipse([x - 180, y - 180, x + 180, y + 180], fill=rgba([GOLD, ROSE, (255, 130, 80)][k % 3], 90 + 40 * math.sin(t + k)))
    for k in range(6):
        x = r.uniform(60, BW - 60) + 16 * math.sin(t * 0.5 + k)
        y = (r.uniform(0, BH) - t * 25 * (0.5 + k % 3 * 0.3)) % (BH + 300) - 150
        if abs(y - BH / 2) < 120: y += 260
        a = r.uniform(-0.4, 0.4) + 0.1 * math.sin(t + k)
        c.d.polygon(rot([(-70, -84), (70, -84), (70, 100), (-70, 100)], a, x, y), fill=(255, 252, 245, 250))
        c.d.polygon(rot([(-58, -72), (58, -72), (58, 60), (-58, 60)], a, x, y), fill=rgba(mix([PINK, SKY, LILAC][k % 3], GOLD, r.uniform(0, .5)), 255))
        c.d.polygon(heart_pts(*rot([(0, -6)], a, x, y)[0], 22, a), fill=rgba(CREAM, 180)) if k % 2 == 0 else \
            c.d.polygon(star_pts(*rot([(0, -6)], a, x, y)[0], 24, 5, 0.45, a), fill=rgba(CREAM, 180))
    out = c.finish(12, 0.8)
    return np.clip(out + grain(int(t * timing.FPS) % 4), 0, 255)

def sc_thorns(t, lt, v, p, e, bt=0.0, blk=None):
    c = Ctx(grad((12, 6, 22), (40, 14, 46), (70, 20, 60)))
    r = R(171)
    grow = min(1, max(0, bt / 4.5))
    bloom = min(1, max(0, (bt - 2.6) / 3.0))
    for k in range(7):
        x0 = BW / 2 + (k - 3) * 70
        n = int((0.5 + 0.5 * grow) * 90 * (1 if k == 3 else r.uniform(0.5, 0.85)))
        pts = [(x0 + 40 * math.sin(i * 0.08 + k) * (1 - (k == 3) * 0.7), BH - i * 8) for i in range(n)]
        if len(pts) > 1:
            c.d.line(pts, fill=(90, 40, 80, 255), width=5)
            for i in range(6, n, 9):
                x, y = pts[i]; sgn = 1 if i % 2 else -1
                c.d.polygon([(x, y - 5), (x + sgn * 16, y - 12), (x, y + 5)], fill=(120, 50, 100, 255))
    tip = (BW / 2 + 40 * math.sin(int((0.5 + 0.5 * grow) * 90) * 0.08 + 3) * 0.3, BH - int((0.5 + 0.5 * grow) * 90) * 8)
    fr = 20 + 90 * bloom * (1 + 0.06 * p)
    if grow > 0.2:
        for layer, col in enumerate([ROSE, PINK, CREAM]):
            flower(c.d, c.g, tip[0], tip[1], fr * (1 - layer * 0.25), t * 0.1 + layer * 0.3, col, GOLD, 6, 240)
    for k in range(40):
        ph, x0 = r.uniform(0, 1), r.uniform(0, BW)
        q = (t * 0.15 + ph) % 1
        c.g.ellipse([x0 - 3, BH - q * BH - 3, x0 + 3, BH - q * BH + 3], fill=rgba([PINK, GOLD][k % 2], 255 * math.sin(q * math.pi) * (0.3 + bloom)))
    out = c.finish(12, 0.8 + 0.6 * bloom)
    return out


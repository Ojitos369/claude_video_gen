# Lyric video renderer: procedural scenes (engine/scenes + optional <project>/scenes.py) + karaoke lyrics.
# H.264 encoder = the best one that works on this machine (settings.local.json -> machine.video_encoder).
#   python engine/render.py <project> --frame 60.2 [..]     -> render/frame_060.20.png (stills for checks)
#   python engine/render.py <project> --preview 119.5 139.5 -> out/preview.mp4
#   python engine/render.py <project> [--force]             -> render/seg_*.mp4 (resumable) + out/<output>
#   python engine/render.py <project> --limit 5             -> at most 5 segments per call; repeat until it muxes the output
# Inputs (project folder): config.json, storyboard.json, audio/beats.json, lyrics/lyrics.json
# --force discards cached segments (needed after editing lyrics/storyboard/config/scenes).
import argparse, json, math, os, subprocess, sys
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from common import project_from_argv, audio_codec, video_encoder_args
from engine import timing, scenes as scene_lib
from engine.timing import snap, pulse, en

PR = project_from_argv()
CFG = PR.cfg
P = PR.p
W, H, FPS = CFG["width"], CFG["height"], CFG["fps"]
BW, BH = CFG.get("scene_canvas") or (540, 960)   # scene design canvas (default vertical 540x960; e.g. [540, 540] for 1:1). Same aspect as output = plain upscale;
VERTICAL = abs(W / H - BW / BH) < 0.01   # other formats: scene centred over a blurred, enlarged copy of itself
S = min(W, H) / 1080         # text scale relative to the 1080-wide design
SEG = CFG["segment_seconds"]

BEATS = json.load(open(P("audio/beats.json"), encoding="utf-8"))
LYR = json.load(open(P("lyrics/lyrics.json"), encoding="utf-8")) if os.path.exists(P("lyrics/lyrics.json")) else {"language": None, "lines": []}   # instrumental: no lyrics
LINES = LYR["lines"]
SB = json.load(open(P("storyboard.json"), encoding="utf-8"))
DUR = BEATS["duration"]
NFRAMES = math.ceil(DUR * FPS)
timing.init(BEATS, FPS)
beats, downs = timing.beats, timing.downs
BG = CFG["background"]
VIDEO_BG = BG.get("type") == "video"
VOX_BG = BG.get("type") == "voxels"   # 3D voxel realms (engine/voxel), scenes in <project>/voxscenes.py
SCENES = {} if VIDEO_BG or VOX_BG else scene_lib.load(PR.dir, BW, BH, CFG["palette"])

MODE = CFG["lyrics_mode"]
if MODE == "auto":
    MODE = {"es": "orig", "en": "orig+es"}.get(LYR.get("language"), "orig+rom+es")

# ---------------------------------------------------------------- timing
SECTIONS = SB.get("sections", [{"start": 0.0, "name": "all", "kind": "verse"}])
def section_at(t):
    s = SECTIONS[0]
    for x in SECTIONS:
        if x["start"] <= t: s = x
    return s

TL = json.load(open(P("audio/timeline.json"), encoding="utf-8")) if os.path.exists(P("audio/timeline.json")) else None   # narrated stories
PAUSES = TL["pauses"] if TL else []

def block_start(b):
    """Block start: "start" (s), "para" (story paragraph; a part's first paragraph starts mid-pause) or "line" (caption index)."""
    if "start" in b: t = b["start"]
    elif "para" in b:
        pi = next((i for i, p in enumerate(TL["parts"]) if p["paras"] == b["para"]), None) if TL else None
        if pi is not None: t = 0.0 if pi == 0 else (PAUSES[pi - 1]["start"] + PAUSES[pi - 1]["end"]) / 2
        else: t = next(l["start"] for l in LINES if l.get("para") == b["para"]) - 0.15
    else: t = LINES[b["line"]]["start"] - 0.15
    return max(0.0, t + b.get("offset", 0))

TR_DUR = 0.3      # default transition length (s); a block can set "tr_dur"
def build_cuts():
    blocks = SB["blocks"]
    bst = [block_start(b) for b in blocks]
    starts = [0.0 if t == 0 else snap(t, beats) for t in bst] + [DUR]
    sec_starts = {round(s["start"], 1) for s in SECTIONS}
    cuts = []
    for i, b in enumerate(blocks):
        t, end, v = starts[i], starts[i + 1], 0
        while True:
            hard = v == 0 and t > 0 and round(bst[i], 1) in sec_starts and section_at(bst[i])["kind"] in ("chorus", "pre", "verse", "outro")
            if v == 0 and "hard" in b: hard = bool(b["hard"]) and t > 0
            # per-block transitions (optional): "transition" for the block's first cut, "transitions" cycled for its inner cuts
            tr = b.get("transition") if v == 0 else (b["transitions"][(v - 1) % len(b["transitions"])] if b.get("transitions") else None)
            cuts.append({"t": t, "motif": b["motif"], "v": v + b.get("v0", 0), "hard": hard, "bstart": starts[i], "blk": b, "tr": tr,
                         "tr_dur": b.get("tr_dur", TR_DUR)})
            nxt = t + b.get("cut_every", 2.0)
            if nxt > end - 1.0: break            # (snapping first could pull a far cut back onto the last beat)
            d = snap(nxt, downs)
            nxt = d if abs(d - nxt) <= 0.45 else snap(nxt, beats)
            ce = b.get("cut_every", 2.0); mn = min(1.0, ce * 0.5)
            if nxt <= t + mn: nxt = t + max(ce, 2.0 if ce >= 2.0 else mn * 2)     # past the last beat: keep advancing
            if nxt > end - mn: break
            t, v = nxt, v + 1
    return cuts
CUTS = [] if VIDEO_BG or VOX_BG else build_cuts()
CUT_T = np.array([c["t"] for c in CUTS])
missing = {c["motif"] for c in CUTS} - set(SCENES)
if missing: sys.exit(f"storyboard uses unknown motifs {missing}; available: {sorted(SCENES)}")

# vignette (bg resolution)
_yy, _xx = np.mgrid[0:BH, 0:BW]
VIG = (1 - 0.55 * (((_xx - BW / 2) / (BW * 0.75)) ** 2 + ((_yy - BH / 2) / (BH * 0.75)) ** 2)).clip(0.35, 1)[..., None].astype(np.float32)

def draw_cut(ci, t, voff=0):
    cut = CUTS[ci]
    lt = t - cut["t"]
    arr = SCENES[cut["motif"]](t, lt, cut["v"] + voff, pulse(t), en(t), t - cut["bstart"], cut["blk"])
    return np.asarray(arr, np.float32)

def pause_amount(t):
    """0..1 blur/dim for the breathing pauses between story parts (eases in before, out after)."""
    for p in PAUSES:
        a, b = p["start"] - 0.45, p["end"] + 0.45
        if a <= t <= b:
            u = min((t - a) / 0.75, (b - t) / 0.75, 1.0)
            return u * u * (3 - 2 * u)
    return 0.0

# ---------------------------------------------------------------- scene transitions
# Storyboard: block "trans" (first cut of the block), "cut_trans" (later cuts inside it), "trans_dur" / "cut_trans_dur";
# top-level "trans" / "cut_trans" are the defaults. Without them: "flash" on section starts, "dissolve" elsewhere (v1 behaviour).
# Kinds: dissolve, flash, zoom, iris, wipe, slide_up, slide_down, slide_left, slide_right, whip, blur, light
# config "transitions" (list, cycled per cut: flash, glitch, slide, zoom, iris, whip, bars) overrides the storyboard kinds.
TRANS = CFG.get("transitions")
RESAMPLE = Image.NEAREST if CFG["scene_resample"] == "nearest" else Image.BILINEAR   # nearest: crisp pixel art
TRANS_DUR = {"dissolve": 0.2, "flash": 0.0, "zoom": 0.45, "iris": 0.5, "wipe": 0.45, "slide_up": 0.4, "slide_down": 0.4,
             "slide_left": 0.4, "slide_right": 0.4, "whip": 0.35, "blur": 0.6, "light": 0.6}
_RAD = np.sqrt(((_xx - BW / 2) / (BW / 2)) ** 2 + ((_yy - BH / 2) / (BW / 2)) ** 2).astype(np.float32)[..., None]
_DIAG = ((_xx / BW) * 0.45 + (_yy / BH) * 0.55).astype(np.float32)[..., None]
_LEAK = np.clip(1 - np.sqrt(((_xx - BW * 0.1) / BW) ** 2 + ((_yy - BH * 0.25) / BH) ** 2) * 1.3, 0, 1).astype(np.float32)[..., None]   # warm light leak mask

def cut_transition(ci):
    c = CUTS[ci]; b = c["blk"]
    if c["v"] == 0:
        name = b.get("trans") or ("flash" if c["hard"] else SB.get("trans", "dissolve")); dur = b.get("trans_dur")
    else:
        name = b.get("cut_trans") or SB.get("cut_trans", "dissolve"); dur = b.get("cut_trans_dur")
    return name, TRANS_DUR.get(name, 0.3) if dur is None else dur

def _zoom(a, z):
    """Centre zoom of a float image (z > 1 enlarges)."""
    if abs(z - 1) < 1e-3: return a
    w, h = BW / z, BH / z
    if z > 1:
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        return np.asarray(im.resize((BW, BH), Image.BILINEAR, box=((BW - w) / 2, (BH - h) / 2, (BW + w) / 2, (BH + h) / 2)), np.float32)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((int(BW * z), int(BH * z)), Image.BILINEAR)
    out = np.zeros_like(a); x0, y0 = (BW - im.width) // 2, (BH - im.height) // 2
    out[y0:y0 + im.height, x0:x0 + im.width] = np.asarray(im, np.float32); return out

def _shift(a, dx, dy):
    """Shift a float image by (dx, dy) px, uncovered area black."""
    dx, dy = int(round(dx)), int(round(dy)); out = np.zeros_like(a)
    ys, yd = (slice(0, BH - dy), slice(dy, BH)) if dy >= 0 else (slice(-dy, BH), slice(0, BH + dy))
    xs, xd = (slice(0, BW - dx), slice(dx, BW)) if dx >= 0 else (slice(-dx, BW), slice(0, BW + dx))
    if abs(dx) < BW and abs(dy) < BH: out[yd, xd] = a[ys, xs]
    return out

def _blur(a, r):
    if r < 0.5: return a
    return np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r)), np.float32)

def transition(name, A, B, k):
    """Storyboard transition: blend the previous cut A into the new cut B; k = 0..1 progress."""
    e = k * k * (3 - 2 * k)
    if name == "zoom":
        out = _zoom(A, 1 + 0.6 * e) * (1 - e) + _zoom(B, 1.3 - 0.3 * e) * e
        return out + (255 - out) * 0.25 * math.sin(math.pi * k)
    if name == "iris":
        r = e * 2.15; m = np.clip((r - _RAD) / 0.1, 0, 1)
        ring = np.exp(-((_RAD - r) / 0.045) ** 2) * 0.7 * (1 - e * 0.5)
        out = A * (1 - m) + B * m
        return out + (np.array([255, 225, 170], np.float32) - out) * ring
    if name == "wipe":
        pos = e * 1.25 - 0.12; m = np.clip((pos - _DIAG) / 0.06, 0, 1)
        ring = np.exp(-((_DIAG - pos) / 0.02) ** 2) * 0.8
        out = A * (1 - m) + B * m
        return out + (255 - out) * ring
    if name.startswith("slide_") or name == "whip":
        dx, dy = {"slide_up": (0, -1), "slide_down": (0, 1), "slide_left": (-1, 0), "slide_right": (1, 0), "whip": (-1, 0)}[name]
        L = BW if dx else BH
        def at(o): return _shift(A, dx * o, dy * o) + _shift(B, dx * (o - L), dy * (o - L))
        if name != "whip": return at(e * L)
        return sum(at((e + j * 0.035) * L) for j in range(-2, 3)) / 5          # whip: motion-blurred push
    if name == "blur":
        out = _blur(A, 28 * e) * (1 - e) + _blur(B, 28 * (1 - e)) * e
        return out + (255 - out) * 0.18 * math.sin(math.pi * k)
    if name == "light":
        out = A * (1 - e) + B * e
        return out + (np.array([255, 196, 150], np.float32) - out) * _LEAK * 0.9 * math.sin(math.pi * k)
    return A * (1 - k) + B * k                                                 # dissolve

def cfg_transition(kind, a, b, u, ci):
    """Blend the previous scene a into the new one b, u = 0..1 over TR_DUR. Each style is an attention-grabbing pattern interrupt."""
    e = 1 - (1 - u) ** 3
    if kind == "cut": return b
    if kind in ("dipwhite", "dipblack"):     # through warm white / black: first half fades out a, second half fades in b
        c = np.array([255, 238, 205], np.float32) if kind == "dipwhite" else np.zeros(3, np.float32)
        k = 1 - abs(2 * u - 1)
        return (a if u < 0.5 else b) * (1 - k) + c * k
    if kind == "flash":
        k = min(1.0, u * 4)
        return (a * (1 - k) + b * k) + (255 - b) * 0.85 * (1 - u) ** 2
    if kind == "glitch":
        out = (a if u < 0.3 else b).copy()
        sh = int(36 * (1 - u))
        out[..., 0] = np.roll(out[..., 0], sh, 1); out[..., 2] = np.roll(out[..., 2], -sh, 1)
        r = np.random.default_rng(ci * 31 + int(u * 8))
        for _ in range(7):
            y0 = int(r.integers(0, BH - 40)); hh = int(r.integers(8, 50)); dx = int(r.integers(-60, 60) * (1 - u))
            out[y0:y0 + hh] = np.roll(out[y0:y0 + hh], dx, 1)
        return out
    if kind == "push":       # the new scene always enters from the right (follows a character walking right)
        off = int(BW * e)
        return np.concatenate([a, b], 1)[:, off:off + BW]
    if kind == "slide":
        off = int(BW * e)
        if ci % 2: return np.concatenate([a, b], 1)[:, off:off + BW]
        return np.concatenate([b, a], 1)[:, BW - off:2 * BW - off]
    if kind == "zoom":
        k = min(1.0, u * 2.2)
        return _zoom(a, 1 + 1.4 * e) * (1 - k) + _zoom(b, 1 + 0.5 * (1 - e)) * k
    if kind == "iris":
        yy, xx = np.ogrid[0:BH, 0:BW]
        rad = e * math.hypot(BW, BH) / 2 * 1.05
        m = ((xx - BW / 2) ** 2 + (yy - BH / 2) ** 2 <= rad * rad)[..., None]
        ring = (np.abs(np.sqrt((xx - BW / 2) ** 2 + (yy - BH / 2) ** 2) - rad) < 7)[..., None] * 255
        return np.where(m, b, a) + ring * (1 - u)
    if kind == "whip":
        n, sh = 7, int(110 * (1 - abs(2 * u - 1)) + 4)
        src = a if u < 0.5 else b
        return sum(np.roll(src, int(sh * (i / n - 0.5)) * (1 if ci % 2 else -1), 1) for i in range(n)) / n
    if kind == "bars":
        k = int(BW / 9)
        idx = (np.arange(BW) // k) % 2
        prog = np.where(idx == 0, e, np.clip(e * 1.6 - 0.3, 0, 1))
        cols = (np.arange(BW) % k) / k < prog
        return np.where(cols[None, :, None], b, a)
    return a * (1 - u) + b * u

def background(t, voff=0, compose=True):
    ci = max(0, int(np.searchsorted(CUT_T, t, side="right") - 1))
    cut = CUTS[ci]
    lt = t - cut["t"]
    img = draw_cut(ci, t, voff)
    kind = section_at(t)["kind"]
    zoom_punch = 0.0
    tname, tdur = cut_transition(ci)
    if ci > 0 and TRANS:
        if lt < TR_DUR: img = cfg_transition(TRANS[ci % len(TRANS)], draw_cut(ci - 1, t, voff), img, lt / TR_DUR, ci)
    elif tname == "flash" and ci > 0:
        zoom_punch = 0.14 * math.exp(-lt / 0.25)
        img = img + (255 - img) * (0.6 * math.exp(-lt / 0.12))            # flash
    elif ci > 0 and cut.get("tr") and lt < cut["tr_dur"]:                  # per-block "transition(s)": cfg styles
        img = cfg_transition(cut["tr"], draw_cut(ci - 1, t, voff), img, lt / cut["tr_dur"], ci)
    elif ci > 0 and lt < tdur:
        img = transition(tname, draw_cut(ci - 1, t, voff), img, lt / tdur)
    if CFG["vignette"]: img = img * VIG
    if CFG["beat_fx"]:
        sh = int(round(3 * pulse(t) ** 1.5))
        if sh: img = img.copy(); img[..., 0] = np.roll(img[..., 0], sh, 1); img[..., 2] = np.roll(img[..., 2], -sh, 1)
    fo = CFG["fade_out"]
    if fo and t > DUR - fo - 0.25:
        img = img * max(0.0, 1 - (t - (DUR - fo - 0.25)) / fo)
    k = pause_amount(t)
    if k > 0: img = img * (1 - 0.6 * k)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if k > 0.02: im = im.filter(ImageFilter.GaussianBlur(16 * k))
    p = pulse(t)
    z = 1.05 + (0.035 if kind == "chorus" else 0.015) * p + 0.02 * math.sin(lt * 0.9 + cut["v"]) + zoom_punch
    drift = (cut["v"] % 3 - 1) * 8 * lt / 2
    if not CFG["camera_motion"]: z, drift = 1.0, 0.0     # scenes move their own camera (e.g. pixel art: exact integer upscale)
    w, h = BW / z, BH / z
    x0, y0 = (BW - w) / 2 + drift, (BH - h) / 2 + 6 * math.sin(lt)
    x0 = min(max(0, x0), BW - w); y0 = min(max(0, y0), BH - h)
    if VERTICAL:
        return im.resize((W, H), RESAMPLE, box=(x0, y0, x0 + w, y0 + h))
    if not compose: return im.resize((int(BW * min(W / BW, H / BH)), int(BH * min(W / BW, H / BH))), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))
    fh = H; fw = int(fh * BW / BH)
    if fw > W: fw = W; fh = int(fw * BH / BW)
    cw = max(W / BW, H / BH)                                   # cover scale for the backdrop
    back = im.resize((int(BW * cw / 4), int(BH * cw / 4)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6))
    back = Image.eval(back.resize((int(BW * cw), int(BH * cw)), Image.BILINEAR), lambda c: int(c * 0.55))
    out = back.crop(((back.width - W) // 2, (back.height - H) // 2, (back.width - W) // 2 + W, (back.height - H) // 2 + H))
    if CFG["wide_panels"] and W - fw >= fw:      # side panels: same cut, other variants, dimmed
        gap = int(CFG["wide_panels"] if CFG["wide_panels"] is not True else 16 * S)
        for k, x in ((1, (W - fw) // 2 - fw - gap), (2, (W + fw) // 2 + gap)):
            side = background(t, k, False).resize((fw, fh))
            out.paste(Image.eval(side, lambda c: int(c * 0.6)), (x, (H - fh) // 2))
    out.paste(im.resize((fw, fh), RESAMPLE, box=(x0, y0, x0 + w, y0 + h)), ((W - fw) // 2, (H - fh) // 2))
    return out

# ---------------------------------------------------------------- lyrics
FONT_B, FONT_R, FI = CFG["font_bold"], CFG["font_regular"], CFG["font_index"]
TC = {k: tuple(v) for k, v in CFG["text_colors"].items()}
MAXW = int(W - 160 * S)
TSZ = CFG["text_size"]
font = lambda path, size: ImageFont.truetype(path, max(8, int(size * S)), index=FI)

class LineGfx:
    def __init__(self, L):
        self.L = L
        words = [w["w"] for w in L["words"]]
        size = TSZ
        while True:
            f = font(FONT_B, size)
            sp = f.getlength(" ")
            wl = [f.getlength(w) for w in words]
            if sum(wl) + sp * (len(words) - 1) <= MAXW or size <= TSZ * 0.76: break
            size -= 4
        rows = [list(range(len(words)))]
        if sum(wl) + sp * (len(words) - 1) > MAXW:     # wrap in 2 balanced rows
            best = None
            for cut in range(1, len(words)):
                a = sum(wl[:cut]) + sp * (cut - 1); b = sum(wl[cut:]) + sp * (len(words) - cut - 1)
                if best is None or max(a, b) < best[0]: best = (max(a, b), cut)
            rows = [list(range(best[1])), list(range(best[1], len(words)))]
        fs, fe = font(FONT_R, 44 * TSZ / 92), font(FONT_R, 46 * TSZ / 92)
        subs = []
        if "rom" in MODE and L.get("rom"): subs.append((L["rom"], fs, TC["rom"]))
        if "es" in MODE and L.get("es"): subs.append((L["es"], fe, TC["tr"]))
        subs = [(self.fit(s, f, MAXW), f, c) for s, f, c in subs]
        mh = int(f.size * 1.28)
        sh = [int(f.size * 1.4) * len(s) for s, f, c in subs]
        pad = int(50 * S)
        bh = mh * len(rows) + int(18 * S) + sum(sh) + pad * 2
        self.w, self.h = W, bh
        base = Image.new("RGBA", (W, bh)); sung = Image.new("RGBA", (W, bh)); gl = Image.new("RGBA", (W, bh))
        db, ds, dg = ImageDraw.Draw(base), ImageDraw.Draw(sung), ImageDraw.Draw(gl)
        self.boxes = []
        y = pad
        for row in rows:
            rw = sum(wl[i] for i in row) + sp * (len(row) - 1)
            x = (W - rw) / 2
            for i in row:
                db.text((x, y), words[i], font=f, fill=TC["unsung"] + (215,), stroke_width=int(6 * S), stroke_fill=TC["outline"] + (235,))
                ds.text((x, y), words[i], font=f, fill=TC["sung"] + (255,), stroke_width=int(6 * S), stroke_fill=TC["outline"] + (255,))
                ds.text((x, y), words[i], font=f, fill=TC["sung"] + (255,))
                dg.text((x, y), words[i], font=f, fill=TC["glow"] + (255,), stroke_width=int(10 * S), stroke_fill=TC["glow"] + (255,))
                self.boxes.append((x - 8 * S, y - 10 * S, x + wl[i] + 8 * S, y + mh))
                x += wl[i] + sp
            y += mh
        y += int(18 * S)
        for lines, fnt, col in subs:
            for s in lines:
                lw = fnt.getlength(s)
                db.text(((W - lw) / 2, y), s, font=fnt, fill=col + (255,), stroke_width=int(4 * S), stroke_fill=TC["outline"] + (240,))
                y += int(fnt.size * 1.4)
        # subtle dark panel behind the text for contrast on bright scenes
        tb = base.getbbox() or (0, 0, W, bh)
        panel = Image.new("RGBA", (W, bh))
        ImageDraw.Draw(panel).rounded_rectangle([tb[0] - 40 * S, tb[1] - 26 * S, tb[2] + 40 * S, tb[3] + 26 * S], int(48 * S), fill=TC["panel"])
        panel = panel.filter(ImageFilter.GaussianBlur(18 * S))
        self.panel, self.text = panel, base
        self.base = Image.alpha_composite(panel, base)
        self.sung = sung
        self.glow = gl.filter(ImageFilter.GaussianBlur(16 * S))

    @staticmethod
    def fit(s, f, maxw):
        if f.getlength(s) <= maxw: return [s]
        ws = s.split(); best = None
        for c in range(1, len(ws)):
            a, b = " ".join(ws[:c]), " ".join(ws[c:])
            m = max(f.getlength(a), f.getlength(b))
            if best is None or m < best[0]: best = (m, [a, b])
        return best[1]

    def render(self, t, kind):
        L = self.L
        mask = Image.new("L", (self.w, self.h))
        md = ImageDraw.Draw(mask)
        active = None
        for w, (x0, y0, x1, y1) in zip(L["words"], self.boxes):
            if t >= w["e"]: md.rectangle([x0, y0, x1, y1], fill=255)
            elif t >= w["s"]:
                k = (t - w["s"]) / max(0.05, w["e"] - w["s"])
                md.rectangle([x0, y0, x0 + (x1 - x0) * k, y1], fill=255); active = (x0, y0, x1, y1)
        if UNSUNG_A < 1:      # words not reached yet stay dim and light up just before they are sung
            dim = Image.new("L", (self.w, self.h), 255); dd = ImageDraw.Draw(dim)
            for w, (x0, y0, x1, y1) in zip(L["words"], self.boxes):
                k = min(1.0, max(0.0, (t - (w["s"] - 0.12)) / 0.12))
                if k < 1: dd.rectangle([x0 - 6 * S, y0 - 14 * S, x1 + 6 * S, y1 + 14 * S], fill=int(255 * (UNSUNG_A + (1 - UNSUNG_A) * k)))
            tx = self.text.copy(); tx.putalpha(Image.fromarray((np.asarray(tx.getchannel("A"), np.uint16) * np.asarray(dim) // 255).astype(np.uint8)))
            img = Image.alpha_composite(self.panel, tx)
        else:
            img = self.base.copy()
        gk = {"chorus": 1.0, "pre": 0.8}.get(kind, 0.6)
        gmask = mask.point(lambda a: int(a * gk))
        img.paste(self.glow, (0, 0), Image.fromarray(np.minimum(np.asarray(gmask), np.asarray(self.glow)[..., 3]).astype(np.uint8)))
        img = Image.alpha_composite(img, Image.composite(self.sung, Image.new("RGBA", img.size), mask))
        return img

GFX = {}
def gfx(i):
    if i not in GFX: GFX[i] = LineGfx(LINES[i])
    return GFX[i]

# Line entrance / exit animation. config: "text_fx" (name or list cycled per line; a storyboard block's "text_fx" wins for
# the lines that start inside it), "text_lead" (s shown before the first word), "text_exit" (s of the exit animation),
# "text_overlap" (true: the old line leaves while the new one enters; false: never shown together).
# Entrances: pop, rise, drop, zoom, blur, wide, swing, flip. "text_unsung_alpha" dims words until they are sung. Exits follow the entrance (rise -> leaves upwards, zoom -> grows...).
TEXT_FX = CFG.get("text_fx", "pop")
LEAD, EXIT, OVERLAP = CFG.get("text_lead", 0.08), CFG.get("text_exit", 0.15), CFG.get("text_overlap", False)
UNSUNG_A = CFG.get("text_unsung_alpha", 1.0)   # < 1: words not sung yet are drawn at this opacity
TIN = max(0.25, LEAD)          # entrance duration

def lyrics_layers(t):
    out = []
    for i, L in enumerate(LINES):
        s, e = L["start"], L["end"]
        nxt = LINES[i + 1]["start"] if i + 1 < len(LINES) else 1e9
        prev_end = LINES[i - 1]["end"] if i else -1
        if OVERLAP:
            fin = min(LEAD, max(0.12, s - prev_end)); fout_end = min(e + EXIT, nxt + 0.25)
        else:
            fin = min(LEAD, max(0.0, s - prev_end)); fout_end = min(e + EXIT, nxt - min(LEAD, max(0.0, nxt - e)) * 0.5) if nxt < 1e9 else e + EXIT
            fout_end = max(fout_end, e + 0.04)
        if t < s - fin or t > fout_end: continue
        u = min(1.0, max(0.0, (t - (s - fin)) / TIN))                     # entrance progress
        q = min(1.0, max(0.0, (t - e) / max(fout_end - e, 1e-3))) if t > e else 0.0   # exit progress
        out.append((i, u, q, t - s))
    return out

def line_fx(i):
    s = LINES[i]["start"]
    if CUTS:
        ci = max(0, int(np.searchsorted(CUT_T, s + 0.05, side="right") - 1))
        if "text_fx" in CUTS[ci]["blk"]: return CUTS[ci]["blk"]["text_fx"]
    return TEXT_FX[i % len(TEXT_FX)] if isinstance(TEXT_FX, list) else TEXT_FX

def animate_line(layer, fx, u, q, pulse_sc):
    """Apply entrance (u: 0->1) and exit (q: 0->1) animation to a lyric layer; returns (layer, dx, dy, alpha)."""
    ei = 1 - (1 - u) ** 3; eo = q * q
    sc, sx, sy, dy, blur, ang = pulse_sc, 1.0, 1.0, 0.0, 0.0, 0.0
    if fx == "pop": sc *= 0.94 + 0.06 * ei
    elif fx == "rise": dy += 80 * S * (1 - ei); blur += 7 * (1 - ei)
    elif fx == "drop": dy -= 80 * S * (1 - ei); blur += 7 * (1 - ei)
    elif fx == "zoom": sc *= 1.35 - 0.35 * ei; blur += 9 * (1 - ei)
    elif fx == "blur": sc *= 1.06 - 0.06 * ei; blur += 16 * (1 - ei)
    elif fx == "wide": sx = 1.3 - 0.3 * ei; blur += 5 * (1 - ei)
    elif fx == "swing": ang = 7 * (1 - ei); dy += 30 * S * (1 - ei)
    elif fx == "flip": sy = 0.12 + 0.88 * ei; blur += 4 * (1 - ei)          # unfolds vertically like a card
    if q > 0:                                                    # exit
        if fx == "flip": sy *= 1 - 0.85 * eo
        elif fx in ("rise", "pop", "swing"): dy -= 70 * S * eo
        elif fx == "drop": dy += 70 * S * eo
        elif fx == "zoom": sc *= 1 + 0.25 * eo
        elif fx == "wide": sx *= 1 + 0.25 * eo
        else: sc *= 1 - 0.08 * eo
        blur += 10 * eo
    alpha = min(1.0, u * 1.6) * (1 - eo)
    if abs(sc - 1) > 0.002 or abs(sx - 1) > 0.002 or abs(sy - 1) > 0.002:
        layer = layer.resize((max(1, int(layer.width * sc * sx)), max(1, int(layer.height * sc * sy))), Image.BILINEAR)
    if ang: layer = layer.rotate(ang, resample=Image.BILINEAR, expand=True)
    if blur > 0.6: layer = layer.filter(ImageFilter.GaussianBlur(blur * S))
    return layer, 0, dy, alpha

# ---------------------------------------------------------------- titles (storyboard "titles": [{start, end, text, sub?, y?, size?,
# font?, sub_font?, color?, glow?, stagger?}]) — letters rise in one by one with blur, the whole title blurs/spreads out at the end.
class TitleGfx:
    def __init__(self, T):
        self.T = T
        f = ImageFont.truetype(T.get("font") or FONT_B, int(T.get("size", 150) * S), index=T.get("font_index", 0))
        col = tuple(T.get("color", TC["sung"])); glow = tuple(T.get("glow", TC["glow"]))
        text = T["text"]
        while f.getlength(text) > W - 100 * S and f.size > 30: f = ImageFont.truetype(T.get("font") or FONT_B, f.size - 6, index=T.get("font_index", 0))
        asc, desc = f.getmetrics(); hh = asc + desc + int(60 * S)
        x = (W - f.getlength(text)) / 2
        self.chars = []
        for ch in text:
            cw = f.getlength(ch)
            if ch.strip():
                pad = int(40 * S)
                im = Image.new("RGBA", (int(cw + 2 * pad + f.size), hh + 2 * pad))
                d = ImageDraw.Draw(im)
                d.text((pad, pad), ch, font=f, fill=glow + (255,), stroke_width=int(8 * S), stroke_fill=glow + (255,))
                g = im.filter(ImageFilter.GaussianBlur(16 * S))
                d2 = ImageDraw.Draw(g)
                d2.text((pad, pad), ch, font=f, fill=col + (255,), stroke_width=int(3 * S), stroke_fill=tuple(TC["outline"]) + (200,))
                self.chars.append((g, int(x - pad), -pad))
            x += cw
        self.h = hh
        self.sub = None
        if T.get("sub"):
            fs = ImageFont.truetype(T.get("sub_font") or FONT_R, int(T.get("sub_size", 52) * S), index=T.get("font_index", 0))
            im = Image.new("RGBA", (W, int(fs.size * 1.8)))
            ImageDraw.Draw(im).text(((W - fs.getlength(T["sub"])) / 2, int(fs.size * 0.3)), T["sub"], font=fs, fill=(255, 255, 255, 235),
                                    stroke_width=int(3 * S), stroke_fill=tuple(TC["outline"]) + (220,))
            self.sub = im

    def render(self, img, t):
        T = self.T; t0, t1 = T["start"], T["end"]
        if t < t0 or t > t1: return
        st = T.get("stagger", 0.07); q = min(1.0, max(0.0, (t - (t1 - 0.7)) / 0.7)); eo = q * q
        layer = Image.new("RGBA", (W, self.h + int(80 * S)))
        for k, (g, x, y) in enumerate(self.chars):
            u = min(1.0, max(0.0, (t - t0 - k * st) / 0.55))
            if u <= 0: continue
            ei = 1 - (1 - u) ** 3
            c = g
            if u < 1: c = c.filter(ImageFilter.GaussianBlur(10 * S * (1 - ei)))
            if u < 1 or eo > 0:
                a = np.asarray(c).copy(); a[..., 3] = (a[..., 3] * min(1.0, u * 1.4)).astype(np.uint8); c = Image.fromarray(a)
            wob = 6 * S * math.sin(t * 2.2 + k * 0.6)
            over(layer, c, x, y + 40 * S + 60 * S * (1 - ei) + wob)
        if eo > 0:
            layer = layer.resize((int(W * (1 + 0.3 * eo)), int(layer.height * (1 + 0.1 * eo))), Image.BILINEAR).filter(ImageFilter.GaussianBlur(14 * S * eo))
            a = np.asarray(layer).copy(); a[..., 3] = (a[..., 3] * (1 - eo)).astype(np.uint8); layer = Image.fromarray(a)
        cy = H * T.get("y", 0.5)
        over(img, layer, (W - layer.width) // 2, cy - layer.height / 2)
        if self.sub is not None:
            u = min(1.0, max(0.0, (t - t0 - T.get("sub_delay", len(self.chars) * st + 0.3)) / 0.6))
            if u > 0:
                s = self.sub
                a = np.asarray(s).copy(); a[..., 3] = (a[..., 3] * u * (1 - eo)).astype(np.uint8); s = Image.fromarray(a)
                over(img, s, 0, cy + self.h * 0.55 + 20 * S * (1 - u))

TITLES = [TitleGfx(T) for T in SB.get("titles", [])]

def over(img, layer, x, y):
    """alpha_composite that accepts layers bigger than the frame or partly outside it."""
    x, y = int(x), int(y)
    cx, cy = max(0, -x), max(0, -y)
    w, h = min(layer.width - cx, img.width - max(0, x)), min(layer.height - cy, img.height - max(0, y))
    if w <= 0 or h <= 0: return
    img.alpha_composite(layer.crop((cx, cy, cx + w, cy + h)), (max(0, x), max(0, y)))

def video_reader(f0):
    """Background video from frame f0: scaled/cropped to the output size, under a black cover (background.dim)."""
    vf = f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    if BG.get("dim", 0.6): vf += f",drawbox=x=0:y=0:w=iw:h=ih:color=black@{BG.get('dim', 0.6)}:t=fill"
    return subprocess.Popen(["ffmpeg", "-loglevel", "error", "-ss", f"{float(f0 / FPS):.4f}", "-i", P(BG["source"]), "-an", "-vf", vf,
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)

_SHOW = None
def vox_show():
    """Created lazily in each worker process (an EGL context must not cross a fork)."""
    global _SHOW
    if _SHOW is None:
        from engine.voxel.show import Show
        _SHOW = Show(PR, BEATS, SB, W, H, FPS)
    return _SHOW

def frame(fi, bg=None):
    t = float(fi / FPS)
    if bg is None and VOX_BG:
        bg = Image.frombytes("RGB", (W, H), vox_show().frame(t)).transpose(Image.FLIP_TOP_BOTTOM)
    img = (bg if bg is not None else background(t)).convert("RGBA")
    kind = section_at(t)["kind"]
    p = pulse(t)
    for T in TITLES: T.render(img, t)
    for i, u, q, since in lyrics_layers(t):
        g = gfx(i)
        layer = g.render(t, kind)
        sc = 1 + ((0.045 if kind == "chorus" else 0.015) * p if CFG["text_pulse"] else 0)
        if CFG["text_anim"] == "dynamic":      # v1 style: per-line punch-in cycled by line index
            dx = dy = 0.0; ang = 0.0; a = min(1.0, u * 1.6) * (1 - q * q)
            uu = max(0.0, min(1.0, since / 0.24)); e3 = 1 - (1 - uu) ** 3; st = i % 4
            if st == 0: sc *= 1 + 0.7 * (1 - e3)
            elif st == 1: dy = 150 * S * (1 - e3)
            elif st == 2: ang = 14 * (1 - e3); sc *= 0.7 + 0.3 * e3
            else: dy = -150 * S * (1 - e3); sc *= 1.15 - 0.15 * e3
            if t > LINES[i]["end"]: sc *= 1 + 0.35 * min(1.0, (t - LINES[i]["end"]) / 0.15)
            if abs(sc - 1) > 0.002: layer = layer.resize((int(g.w * sc), int(g.h * sc)), Image.BILINEAR)
            if ang: layer = layer.rotate(ang * (1 if i % 8 < 4 else -1), expand=True, resample=Image.BILINEAR)
        else:
            layer, dx, dy, a = animate_line(layer, line_fx(i), u, q, sc)
        if a <= 0.01: continue
        if a < 1:
            al = np.asarray(layer).copy(); al[..., 3] = (al[..., 3] * a).astype(np.uint8); layer = Image.fromarray(al)
        cy = H * 0.8 if CFG["caption_position"] == "bottom" else H / 2
        over(img, layer, (W - layer.width) / 2 + dx, cy - layer.height / 2 + dy)
    return img.convert("RGB")

# ---------------------------------------------------------------- encode
def ff_writer(path):
    return subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             *video_encoder_args(PR.machine, CFG["nvenc_cq"]), "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)

def render_range(args):
    f0, f1, path = args
    tmp = path + ".part.mp4"
    pr = ff_writer(tmp)
    rd = video_reader(f0) if VIDEO_BG else None
    last = None
    for fi in range(f0, f1):
        bg = None
        if rd:
            buf = rd.stdout.read(W * H * 3)
            if len(buf) == W * H * 3: last = Image.frombytes("RGB", (W, H), buf)
            bg = last if last is not None else Image.new("RGB", (W, H))   # source shorter than audio: hold last frame
        pr.stdin.write(frame(fi, bg).tobytes())
    pr.stdin.close(); pr.wait()
    if rd: rd.kill(); rd.wait()
    os.replace(tmp, path)
    return path

def mux(video, out, t0=0.0, dur=None):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-ss", f"{t0:.3f}"] + (["-t", f"{dur:.3f}"] if dur else []) + \
          ["-i", PR.audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy"] + (["-c:a", "copy"] if audio_codec(PR.audio) == "aac" and not dur else ["-c:a", "aac", "-b:a", CFG["audio_bitrate"]]) + ["-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", nargs=2, type=float)
    ap.add_argument("--frame", type=float, nargs="+")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--jobs", type=int, default=CFG["jobs"])
    ap.add_argument("--limit", type=int, help="render at most N segments in this call (long renders in several runs)")
    a = ap.parse_args()
    os.makedirs(P("out"), exist_ok=True)
    if a.frame:
        for t in a.frame:
            fi = int(round(t * FPS)); bg = None
            if VIDEO_BG:
                rd = video_reader(fi); bg = Image.frombytes("RGB", (W, H), rd.stdout.read(W * H * 3)); rd.kill()
            frame(fi, bg).save(PR.rdir(f"frame_{t:06.2f}.png")); print("saved", t)
        sys.exit()
    if a.preview:
        t0, t1 = a.preview
        f0, f1 = int(t0 * FPS), int(t1 * FPS)
        n = max(1, a.jobs)
        step = math.ceil((f1 - f0) / n)
        parts = [(s, min(f1, s + step), PR.rdir(f"preview_{i:02d}.mp4")) for i, s in enumerate(range(f0, f1, step))]
        with Pool(n) as pool: pool.map(render_range, parts)
        lst = PR.rdir("preview_list.txt")
        open(lst, "w", encoding="utf-8").write("".join(f"file '{x[2]}'\n" for x in parts))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", PR.rdir("preview_v.mp4")], check=True)
        mux(PR.rdir("preview_v.mp4"), PR.out_name("preview.mp4"), float(f0 / FPS), float((f1 - f0) / FPS))
        print("out/preview.mp4"); sys.exit()
    segs = []
    for i, f0 in enumerate(range(0, NFRAMES, int(round(SEG * FPS)))):
        path = PR.rdir(f"seg_{i:03d}.mp4")
        if a.force and os.path.exists(path): os.remove(path)
        segs.append((f0, min(NFRAMES, f0 + int(round(SEG * FPS))), path))
    todo = [s for s in segs if not os.path.exists(s[2])]
    print(f"{len(segs)} segments, {len(todo)} to render, {NFRAMES} frames")
    left = todo[a.limit:] if a.limit else []
    if a.limit: todo = todo[:a.limit]
    with Pool(a.jobs) as pool:
        for pth in pool.imap_unordered(render_range, todo): print("done", os.path.basename(pth), flush=True)
    if left:
        print(f"{len(left)} segments left: run again (without --force) to continue"); sys.exit()
    lst = PR.rdir("segments.txt")
    open(lst, "w", encoding="utf-8").write("".join(f"file '{s[2]}'\n" for s in segs))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", PR.rdir("full_v.mp4")], check=True)
    mux(PR.rdir("full_v.mp4"), PR.output)
    print(PR.output)
